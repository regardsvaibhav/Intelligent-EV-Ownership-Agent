"""
Intent-accuracy evaluation on clean text and on simulated STT errors.

    python eval_intents.py            # prints tables and writes eval_results.md

STT-error simulator (simulate_stt_errors): for each word, with probability p,
apply ONE of these corruptions (chosen uniformly, deterministic per seed):
    drop_char     delete one character            "चार्जिंग" -> "चार्जिग"
    swap_chars    swap two adjacent characters    "kitna"   -> "iktna"
    dup_char      duplicate one character         "kharcha" -> "kharchha"
    script_swap   Devanagari <-> romanized form   "कितना"   -> "kitna"   (from a small word list)
    drop_word     the word disappears
    merge         word glued to the next word     "kitna chalega" -> "kitnachalega"
This is a rough stand-in for ASR mistakes, not a model of Gnani Prisma's real
error distribution. Real-audio numbers come from noise_test.py.

Each utterance is evaluated in a fresh Session (single turn). A prediction counts
as correct if the expected intent is the primary intent or one of the intents run
together (e.g. range + charge_time_cost). "clarify" counts as wrong.
"""
import os
import random
from collections import Counter, defaultdict

os.environ.setdefault("EV_AGENT_LOG_PATH", "")

import agent  # noqa: E402
from eval_set import EVAL_SET  # noqa: E402

NOISE_LEVELS = [0.1, 0.2, 0.3]
SAMPLES_PER_UTTERANCE = 10
CONFUSION_LEVEL = 0.2

SCRIPT_PAIRS = {
    "चार्ज": "charge", "चार्जर": "charger", "चार्जिंग": "charging", "कितना": "kitna", "कितनी": "kitni",
    "चलेगा": "chalega", "चलेगी": "chalegi", "खर्चा": "kharcha", "जाना": "jana", "है": "hai", "में": "mein",
    "नहीं": "nahi", "बैटरी": "battery", "स्टेशन": "station", "कहां": "kahan", "प्रतिशत": "percent",
    "किलोमीटर": "kilometer", "धुआं": "dhuan", "पहुंच": "pahunch", "बचा": "bacha", "आज": "aaj", "धीमी": "dheemi",
    "रेंज": "range", "कम": "kam", "पेट्रोल": "petrol", "सफर": "safar", "से": "se", "पास": "paas", "हो": "ho",
    "रहा": "raha", "रही": "rahi", "गई": "gayi", "गया": "gaya", "बहुत": "bahut", "पूरा": "poora", "देर": "der",
}
SCRIPT_PAIRS.update({v: k for k, v in list(SCRIPT_PAIRS.items())})
OPS = ["drop_char", "swap_chars", "dup_char", "script_swap", "drop_word", "merge"]


def simulate_stt_errors(text, p, rng):
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        w = words[i]
        if rng.random() >= p or not w:
            out.append(w)
            i += 1
            continue
        op = rng.choice(OPS)
        bare = w.strip("?,.!।")
        if op == "drop_char" and len(w) > 2:
            k = rng.randrange(len(w))
            w = w[:k] + w[k + 1:]
        elif op == "swap_chars" and len(w) > 2:
            k = rng.randrange(len(w) - 1)
            w = w[:k] + w[k + 1] + w[k] + w[k + 2:]
        elif op == "dup_char" and w:
            k = rng.randrange(len(w))
            w = w[:k] + w[k] + w[k:]
        elif op == "script_swap" and bare.lower() in SCRIPT_PAIRS:
            w = SCRIPT_PAIRS[bare.lower()]
        elif op == "drop_word":
            i += 1
            continue
        elif op == "merge" and i + 1 < len(words):
            w = w + words[i + 1]
            i += 1
        out.append(w)
        i += 1
    return " ".join(out)


def predict(text):
    r = agent.step(agent.Session(), text, log=False)
    return r["intent"], r["intents"]


def is_correct(label, intent, intents):
    return label == intent or label in intents


def evaluate(pairs):
    per = defaultdict(lambda: [0, 0])
    confusion = Counter()
    correct = 0
    for text, label in pairs:
        intent, intents = predict(text)
        ok = is_correct(label, intent, intents)
        correct += ok
        per[label][0] += ok
        per[label][1] += 1
        confusion[(label, label if ok else intent)] += 1
    return correct / len(pairs), per, confusion


def noisy_pairs(p, samples=SAMPLES_PER_UTTERANCE, seed=1234):
    rng = random.Random(seed)
    return [(simulate_stt_errors(text, p, rng), label) for text, label in EVAL_SET for _ in range(samples)]


def confusion_table(confusion, labels):
    preds = sorted({pr for (_, pr) in confusion} | set(labels))
    short = {x: x.replace("trouble_", "t_").replace("charge_time_cost", "time_cost") for x in preds}
    head = "| expected \\ predicted | " + " | ".join(short[p] for p in preds) + " |"
    sep = "|" + "---|" * (len(preds) + 1)
    rows = [head, sep]
    for lab in labels:
        rows.append(f"| {short[lab]} | " + " | ".join(str(confusion.get((lab, p), "")) for p in preds) + " |")
    return "\n".join(rows)


def main():
    labels = sorted({lab for _, lab in EVAL_SET})
    clean_acc, clean_per, clean_conf = evaluate(EVAL_SET)
    results = [("clean", 0.0, clean_acc, clean_per, len(EVAL_SET))]
    conf_noisy = None
    for p in NOISE_LEVELS:
        pairs = noisy_pairs(p)
        acc, per, conf = evaluate(pairs)
        results.append((f"noisy p={p}", p, acc, per, len(pairs)))
        if p == CONFUSION_LEVEL:
            conf_noisy = conf

    lines = ["# Intent evaluation results", "",
             f"Eval set: {len(EVAL_SET)} labelled synthetic utterances (`eval_set.py`), {len(labels)} intents. "
             f"Noisy sets: each utterance corrupted {SAMPLES_PER_UTTERANCE} times per level with "
             "`simulate_stt_errors` (seeded, reproducible).", "",
             "| condition | utterances | accuracy |", "|---|---|---|"]
    for name, p, acc, per, n in results:
        lines.append(f"| {name} | {n} | {acc * 100:.1f}% |")
    lines += ["", "## Per-intent accuracy", "",
              "| intent | " + " | ".join(r[0] for r in results) + " |",
              "|" + "---|" * (len(results) + 1)]
    for lab in labels:
        cells = []
        for _, _, _, per, _ in results:
            c, n = per[lab]
            cells.append(f"{c / n * 100:.0f}%")
        lines.append(f"| {lab} | " + " | ".join(cells) + " |")
    lines += ["", f"## Confusion table (noisy p={CONFUSION_LEVEL})", "",
              "Rows = expected intent, columns = predicted. `clarify` means the agent asked a question "
              "instead of guessing; it is counted as wrong.", "",
              confusion_table(conf_noisy, labels), "",
              "## Caveats", "",
              "- The eval set was written by the same author as the rules, before the rules were implemented. "
              "On the first run, before any rule changes, clean accuracy was 48/50 (96%). Two keyword gaps found "
              "by that run were then fixed (`range bahut ghat gayi`, `करंट लगा`), so the clean number in the table above is "
              "optimistic.",
              "- After the first noisy run, two more changes were made because of what it showed: safety keywords "
              "use fuzzy matching (safety was at 77% for p=0.2; fuzzy is limited to distinctive words after "
              "'jana' was found to fuzzy-match 'jalna'), and 'hi' counts as a greeting only as the "
              "first word (Hindi 'hi' = 'even'). The noisy numbers above are after those changes.",
              "- The STT-error simulator is synthetic. It is not a measurement of Gnani Prisma's error rate.",
              "- No embedding classifier is included, so there is no 'with embeddings' column."]
    report = "\n".join(lines) + "\n"
    with open("eval_results.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
