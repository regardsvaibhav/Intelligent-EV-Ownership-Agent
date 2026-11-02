E-RICKSHAW VOICE AGENT - kaise chalana hai
===========================================
Aapko koi code likhna nahi hai. Bas neeche ke kadam copy-paste karo.

KADAM 1: Python (ek baar)
- python.org se Python 3.10 ya naya install karo.
  Windows par install karte waqt "Add Python to PATH" ka box TICK karna.

KADAM 2: API key
- .env file ko Notepad se kholo.
- PASTE_YOUR_API_KEY_HERE ki jagah apni Gnani API key paste karo. Kuch aur mat badalna. Save karo.
  (Key kisi ko mat bhejna, GitHub par mat daalna.)

KADAM 3: Terminal kholo is folder mein
- Windows: folder kholo, upar address bar mein "cmd" likho, Enter dabao.
- Mac: folder par right-click -> New Terminal at Folder.

KADAM 4: Libraries install (ek baar) - ye line paste karke Enter:
    pip install -r requirements.txt

KADAM 5: Pehle bina key ke logic test karo (optional):
    python agent.py

KADAM 6: App chalao (ye Flask app hai, Streamlit nahi):
    python app.py
- Phir browser (Chrome) mein kholo:  http://localhost:5000
- Hari "बोलिए" button dabao, Hinglish mein bolo, dobara button dabao.
- Pehle chips (neeche ke buttons) dabake dekho. Wo bina mic ke chalte hain.

`streamlit run app.py` mat chalao. Is folder ka `app.py` Flask server hai, isliye
Streamlit mein blank page dikhega.

DEPLOYMENT (Render par)
-----------------------
1. Is `v2/ev-agent` folder ko GitHub repository mein push karo. `.env` ko kabhi
   GitHub par push mat karo; API key ke liye `.env.example` sirf template hai.
2. render.com par account banao, New -> Web Service chuno, aur repository connect karo.
3. Root Directory mein `v2/ev-agent` set karo (agar repository ke root mein ye folder hai).
4. Runtime `Python 3` rakho.
5. Build Command:
       pip install -r requirements.txt
6. Start Command:
       gunicorn --bind 0.0.0.0:$PORT app:app
7. Environment Variables mein `GNANI_API_KEY` naam se apni key add karo. Value
   `.env` se copy karo, quotes ke bina.
8. Deploy ke baad Render ka URL kholo. Health check ke liye URL ke end mein `/`
   lagao.

Local production-style check:
       pip install -r requirements.txt
       gunicorn --bind 127.0.0.1:5000 app:app

Important:
- Browser microphone permission HTTPS deployment par hi reliably kaam karegi.
- Gnani API calls server se hoti hain; API key browser code mein nahi jaati.
- Free hosting service sleep kar sakti hai, isliye pehli request slow ho sakti hai.

NOISE TEST (interview ke liye)
1. App chalu karke 5-10 chhote sawaal bolo. Har jawab ke upar "WAV mein save karo" link aata hai.
   Un files ko test_clips folder mein clip1.wav, clip2.wav... naam se rakho.
2. Terminal mein:   python noise_test.py
   Ye har clip ka saaf transcript .txt mein likh dega.
3. Har .txt kholo, galti ho to theek karo (Devanagari mein). Save karo.
4. Dobara:          python noise_test.py
   results.csv aur noisy_clips/ (shor wali awaaz) banega. Summary mein saaf vs shor wali accuracy dikhegi.

AGAR KUCH ATKE
- "API key nahi mili"          -> KADAM 2 dobara.
- "Prisma error 401/403"       -> key galat hai ya credits khatam.
- "Timbre error ..."           -> gnani.py mein TTS_VOICE aur TTS_MODEL ko current TTS REST docs ke hisaab se badlo.
- Prisma error 4xx / transcript khali -> gnani.py ki STT_URL aur STT_LANGUAGE docs se match karo.
- Jo error aaye wo poora yahan Claude ko paste kar do.

NUMBERS BADALNA
- agent.py ke upar BATTERY_KWH, FULL_RANGE_KM, CHARGER_KW, TARIFF_RS_PER_UNIT hain.
  Ye andaazan (assumed) numbers hain. Apne e-rickshaw ke asli numbers daal sakte ho.

DATA
- Sab charging stations nakli (synthetic) hain. Koi real number ya jagah nahi.
