"""
Labelled single-turn utterances for eval_intents.py.

Written BEFORE the new NLU rules were implemented, and kept separate from
tests/test_agent.py, so that it is not simply a copy of the keyword lists.
It is still written by the same person who wrote the rules, so clean-text
accuracy on it is an optimistic estimate, not a field measurement.

All utterances are synthetic. Each entry: (utterance, expected_intent).
"""

EVAL_SET = [
    # range
    ("50 प्रतिशत चार्ज है, कितना चलेगी गाड़ी?", "range"),
    ("battery 70 percent hai, kitni door tak jayegi", "range"),
    ("अस्सी परसेंट पर रेंज कितनी मिलेगी", "range"),
    ("bhai 45% hai kitne km chalega", "range"),
    ("तीस प्रतिशत बैटरी में कहां तक चलेगी", "range"),
    # charge_time_cost
    ("20 percent se full charge mein kitna time lagega", "charge_time_cost"),
    ("पूरा चार्ज करने में कितना खर्चा आएगा, अभी 40% है", "charge_time_cost"),
    ("charging ka bill kitna banega 35 percent se", "charge_time_cost"),
    ("पचास प्रतिशत से फुल होने में कितने घंटे", "charge_time_cost"),
    ("kitne paise lagenge charge karne mein, 60% hai", "charge_time_cost"),
    # trip
    ("भोपाल से सीहोर जाना है, पहुंच जाऊंगा?", "trip"),
    ("indore se dewas jaana hai 50 percent charge mein", "trip"),
    ("30 km jana hai, 40% battery hai, pahunch jaunga kya", "trip"),
    ("उदयपुर से नाथद्वारा तक जा पाऊंगा क्या", "trip"),
    ("pachas kilometer ka safar hai, chal paunga?", "trip"),
    # stations
    ("जयपुर में चार्जिंग स्टेशन कहां है", "stations"),
    ("indore mein charging point batao", "stations"),
    ("paas mein koi charging station hai kya", "stations"),
    ("भरतपुर में कहां चार्ज करूं", "stations"),
    ("bhopal mein charge kahan karu", "stations"),
    # savings
    ("आज 90 किलोमीटर चलाया, कितना बचा?", "savings"),
    ("petrol auto ke mukable kitni bachat hui aaj 60 km", "savings"),
    ("सीएनजी से कितना सस्ता पड़ा आज", "savings"),
    ("aaj 100 km chalayi, paisa kitna bacha", "savings"),
    # trouble_slow_charging
    ("चार्जिंग बहुत धीमी हो रही है", "trouble_slow_charging"),
    ("charge hone mein bahut der lag rahi hai", "trouble_slow_charging"),
    ("charging slow hai aajkal", "trouble_slow_charging"),
    ("बैटरी बहुत धीरे चार्ज हो रही है", "trouble_slow_charging"),
    # trouble_range_drop
    ("गाड़ी पहले जितना नहीं चलती, रेंज कम हो गई", "trouble_range_drop"),
    ("range bahut ghat gayi hai", "trouble_range_drop"),
    ("mileage kam de rahi hai", "trouble_range_drop"),
    ("पहले 90 चलती थी अब 60 चलती है", "trouble_range_drop"),
    # trouble_not_detecting
    ("चार्जर लगाया पर चार्ज नहीं हो रहा", "trouble_not_detecting"),
    ("charger ki light hi nahi jal rahi", "trouble_not_detecting"),
    ("charger connect nahi ho raha", "trouble_not_detecting"),
    ("चार्जिंग शुरू ही नहीं हो रही", "trouble_not_detecting"),
    # safety
    ("चार्जर में से धुआं निकल रहा है", "safety"),
    ("battery bahut garam ho gayi hai", "safety"),
    ("plug mein chingari aa rahi hai", "safety"),
    ("चार्ज करते समय करंट लगा", "safety"),
    ("तार पिघल गया है", "safety"),
    ("charger se jalne ki badbu aa rahi hai", "safety"),
    # greeting
    ("नमस्ते", "greeting"),
    ("ram ram bhaiya", "greeting"),
    ("hello ji", "greeting"),
    # fallback (out of domain)
    ("आज मौसम कैसा है", "fallback"),
    ("cricket ka score kya hua", "fallback"),
    ("mujhe chai peeni hai", "fallback"),
    ("गाना सुनाओ", "fallback"),
    ("मेरा नाम राजू है", "fallback"),
]
