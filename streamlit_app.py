import streamlit as st
import google.generativeai as genai
from newsapi import NewsApiClient
from serpapi import GoogleSearch
import threading
from streamlit_oauth import OAuth2Component
import jwt
import pymongo
from datetime import datetime
import requests

# --- PAGE CONFIG ---
st.set_page_config(page_title="Bangalore Pulse", page_icon="🔮", layout="wide")

# --- CUSTOM CSS FOR "NEON PULSE" STYLING (FIXED) ---
def load_css():
    # REMOVED the 'f' from f"""...""" to fix the SyntaxError
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@700&family=Inter:wght@400;600&display=swap');
            html, body, [class*="st-"] { font-family: 'Inter', sans-serif; color: #FAFAFA; }
            h1, h2, h3 { font-family: 'Poppins', sans-serif; font-weight: 700; color: #FAFAFA; }
            .st-emotion-cache-1y4p8pa, .st-emotion-cache-uf99v8 { background: none; }
            h1 { text-shadow: 0 0 10px #F600FF, 0 0 20px #F600FF; }
            .stButton>button { border-radius: 10px; border: 2px solid #F600FF; color: #F600FF; background-color: transparent; transition: all 0.3s ease-in-out; font-weight: bold; text-shadow: 0 0 5px #F600FF; }
            .stButton>button:hover { background-color: #F600FF; color: #FFFFFF; box-shadow: 0 0 15px #F600FF; }
            [data-testid="stMetric"], [data-testid="stExpander"], [data-testid="stInfo"], [data-testid="stWarning"] { background: rgba(45, 52, 71, 0.5); backdrop-filter: blur(10px); border-radius: 15px; padding: 1rem 1.5rem; border: 1px solid rgba(255, 255, 255, 0.18); }
            [data-testid="stMetricLabel"] { color: #FAFAFA; text-shadow: 0 0 5px #F600FF; }
        </style>
    """, unsafe_allow_html=True)

# --- (All your API Clients, DB Connection, Functions, etc. remain the same) ---
AUTH0_CLIENT_ID,AUTH0_CLIENT_SECRET,AUTH0_DOMAIN,AUTH0_REDIRECT_URI=st.secrets["AUTH0_CLIENT_ID"],st.secrets["AUTH0_CLIENT_SECRET"],st.secrets["AUTH0_DOMAIN"],"http://localhost:8501"
oauth2 = OAuth2Component(client_id=AUTH0_CLIENT_ID, client_secret=AUTH0_CLIENT_SECRET, authorize_endpoint=f"https://{AUTH0_DOMAIN}/authorize", token_endpoint=f"https://{AUTH0_DOMAIN}/oauth/token")
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
gemini_model = genai.GenerativeModel('gemini-1.5-flash')
newsapi = NewsApiClient(api_key=st.secrets["NEWS_API_KEY"])
mongo_client = pymongo.MongoClient(st.secrets["MONGO_URI"])
db = mongo_client.bangalore_pulse_db
history_collection = db.history
BANGALORE_COORDS = {"koramangala": [12.9357, 77.6245], "indiranagar": [12.9784, 77.6408], "jayanagar": [12.9309, 77.5838], "hsr layout": [12.9121, 77.6446], "whitefield": [12.9698, 77.7499]}
def get_news_articles(q,c):
    try: a=newsapi.get_everything(q=f"{q} Bangalore",language='en',sort_by='relevancy',page_size=5);c.extend(a.get('articles',[]))
    except Exception as e:print(f"NewsAPI Error: {e}")
def get_contextual_data(q,c):
    p={"engine":"google","q":f"what is happening in {q} Bangalore","api_key":st.secrets["SERPAPI_API_KEY"]}
    try: s=GoogleSearch(p);r=s.get_dict();c.extend(filter(None,[i.get('snippet','')for i in r.get('organic_results',[])]))
    except Exception as e:print(f"SerpApi Context Error: {e}")
def get_local_places(q,c):
    p={"engine":"google_local","q":f"top cafes restaurants in {q} Bangalore","api_key":st.secrets["SERPAPI_API_KEY"]}
    try: s=GoogleSearch(p);r=s.get_dict();c.extend([f"{i.get('title')} (Rating: {i.get('rating','N/A')})"for i in r.get('local_results',[])])
    except Exception as e:print(f"SerpApi Places Error: {e}")
def get_weather(q,c):
    try: a=st.secrets["WEATHER_API_KEY"];u=f"http://api.weatherapi.com/v1/current.json?key={a}&q={q},India";r=requests.get(u);r.raise_for_status();d=r.json();c['temp']=d['current']['temp_c'];c['status']=d['current']['condition']['text']
    except Exception as e:print(f"Weather Error: {e}")
def get_gemini_vibe_check(a,c,p,w,ar):
    if not any([a,c,p,w]):return"Could not find recent data."
    at=" ".join([f"{i['title']}. {i.get('description','')}"for i in a]);ct=" ".join(c);pt=" | ".join(p);wt=f"Temp is {w.get('temp')}°C with {w.get('status')}."
    pr=f"""Analyze data for {ar}, Bangalore. Output must be concise markdown. 1. Vibe summary. 2. "Pulse Points" (traffic, safety). 3. "Top Spots" (recommendations). 4. "Weather & Attire". Data: News: "{at}", Web: "{ct}", Places: "{pt}", Weather: "{wt}" """
    try: return gemini_model.generate_content(pr).text
    except Exception as e:return f"Error: {e}"
def save_search(e,a):
    try: history_collection.insert_one({"email":e,"area":a,"timestamp":datetime.utcnow()})
    except Exception as e:print(f"MongoDB Save Error: {e}")
def get_search_history(e):
    try: p=[{"$match":{"email":e}},{"$sort":{"timestamp":-1}},{"$group":{"_id":"$area"}},{"$limit":5}];return[d["_id"]for d in history_collection.aggregate(p)]
    except Exception as e:print(f"MongoDB History Error: {e}");return[]

# --- MAIN APP WRAPPER ---
def main():
    load_css()
    st.markdown("""
        <div style="
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: linear-gradient(-45deg, #0E1117, #1a1a2e, #1E0034, #0E1117);
            background-size: 400% 400%;
            animation: gradientAnimation 15s ease infinite;
        "></div>
    """, unsafe_allow_html=True)

    if 'token' not in st.session_state:
        st.title("Bangalore Pulse 🔮"); st.markdown("### Your AI guide to the city's real-time vibe.")
        st.markdown("---")
        r=oauth2.authorize_button(name="Login to Get Started",icon="https://auth0.com/favicon.ico",redirect_uri=AUTH0_REDIRECT_URI,scope="openid email profile",key="auth0")
        if r and"token"in r:st.session_state.token=r.get("token");st.rerun()
    else:
        t=st.session_state.get('token');ui=jwt.decode(t['id_token'],options={"verify_signature":False});ue=ui.get('email')
        st.sidebar.title(f"Welcome, {ui.get('name','User')}!"); st.sidebar.write(ue)
        if st.sidebar.button("Logout",key="logout_button"):del st.session_state.token;st.rerun()
        st.sidebar.markdown("---"); st.sidebar.subheader("Recent Searches")
        sh=get_search_history(ue)
        for i in sh:
            if st.sidebar.button(i.title(),key=f"history_{i}"):st.session_state.area_input=i;st.rerun()
        
        st.title("Bangalore Pulse 🔮")
        ai=st.text_input("Search a neighborhood...",value=st.session_state.get("area_input",""),placeholder="e.g., Koramangala",label_visibility="collapsed",key="area_input").lower()
        if st.button("Get Pulse",key="pulse_button"):
            if ai:
                save_search(ue,ai)
                with st.spinner(f"Taking the pulse of {ai}..."):
                    nr,cr,pr,wr=[],[],[],{}
                    ths=[threading.Thread(target=get_news_articles,args=(ai,nr)),threading.Thread(target=get_contextual_data,args=(ai,cr)),threading.Thread(target=get_local_places,args=(ai,pr)),threading.Thread(target=get_weather,args=(ai,wr))]
                    for t in ths:t.start()
                    for t in ths:t.join()
                    vs=get_gemini_vibe_check(nr,cr,pr,wr,ai)
                    
                    st.header(f"Live Pulse: {ai.title()}")
                    mc1,mc2=st.columns(2)
                    with mc1:
                        if wr: st.metric(f"☀️ Weather",f"{wr.get('temp','N/A')}°C",wr.get('status',''))
                    with mc2:
                        sl=vs.lower()
                        if any(w in sl for w in ["chaotic","alert","heavy traffic"]):vs_=("🔴 Alert","High activity")
                        elif any(w in sl for w in ["busy","buzzing","active"]):vs_=("🟠 Active","Lively")
                        else:vs_=("🟢 Calm","Peaceful")
                        st.metric("🚦 Vibe",vs_[0],vs_[1])

                    st.markdown("---"); st.markdown(vs)
                    if pr:
                        with st.expander("⭐ See Top Rated Spots Nearby",expanded=True):
                            for p in pr[:3]:st.info(p)
            else:st.warning("Please enter a neighborhood.")

if __name__=='__main__':
    main()