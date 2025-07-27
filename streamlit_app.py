import streamlit as st
import google.generativeai as genai
from newsapi import NewsApiClient
from serpapi import GoogleSearch
import threading
from streamlit_oauth import OAuth2Component
import jwt
import pymongo
from datetime import datetime
import requests # New import for weather

# --- PAGE CONFIG ---
st.set_page_config(page_title="Bangalore Pulse", page_icon="🔴", layout="wide")

# --- AUTH0 CONFIGURATION ---
AUTH0_CLIENT_ID = st.secrets["AUTH0_CLIENT_ID"]
AUTH0_CLIENT_SECRET = st.secrets["AUTH0_CLIENT_SECRET"]
AUTH0_DOMAIN = st.secrets["AUTH0_DOMAIN"]
AUTH0_REDIRECT_URI = "http://localhost:8501"

oauth2 = OAuth2Component(
    client_id=AUTH0_CLIENT_ID, client_secret=AUTH0_CLIENT_SECRET,
    authorize_endpoint=f"https://{AUTH0_DOMAIN}/authorize",
    token_endpoint=f"https://{AUTH0_DOMAIN}/oauth/token",
)

# --- API CLIENTS & MODEL ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
gemini_model = genai.GenerativeModel('gemini-1.5-flash')
newsapi = NewsApiClient(api_key=st.secrets["NEWS_API_KEY"])
# pyowm client is removed

# --- DATABASE CONNECTION ---
try:
    mongo_client = pymongo.MongoClient(st.secrets["MONGO_URI"])
    db = mongo_client.bangalore_pulse_db
    history_collection = db.history
except Exception as e:
    st.error(f"Database Error: {e}")
    st.stop()

# --- DATA & COORDINATES ---
BANGALORE_COORDS = {
    "koramangala": [12.9357, 77.6245], "indiranagar": [12.9784, 77.6408],
    "jayanagar": [12.9309, 77.5838], "hsr layout": [12.9121, 77.6446],
    "whitefield": [12.9698, 77.7499]
}

# --- FUNCTIONS ---
def get_news_articles(query, container):
    try:
        articles = newsapi.get_everything(q=f"{query} Bangalore", language='en', sort_by='relevancy', page_size=5)
        container.extend(articles.get('articles', []))
    except Exception as e: print(f"NewsAPI Error: {e}")

def get_contextual_data(query, container):
    params = {"engine": "google", "q": f"what is happening in {query} Bangalore", "api_key": st.secrets["SERPAPI_API_KEY"]}
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        snippets = [res.get('snippet', '') for res in results.get('organic_results', [])]
        container.extend(filter(None, snippets))
    except Exception as e: print(f"SerpApi Context Error: {e}")

def get_local_places(query, container):
    params = {"engine": "google_local", "q": f"top cafes restaurants in {query} Bangalore", "api_key": st.secrets["SERPAPI_API_KEY"]}
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        places = [f"{place.get('title')} (Rating: {place.get('rating', 'N/A')})" for place in results.get('local_results', [])]
        container.extend(places)
    except Exception as e: print(f"SerpApi Places Error: {e}")

def get_weather(query, container):
    """Fetches weather data from WeatherAPI.com."""
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={query},India"
        response = requests.get(url)
        response.raise_for_status() # Raises an exception for bad status codes
        data = response.json()
        container['temp'] = data['current']['temp_c']
        container['status'] = data['current']['condition']['text']
    except Exception as e: 
        print(f"Weather Error: {e}")

def get_gemini_vibe_check(articles, context, places, weather, area):
    if not any([articles, context, places, weather]): return "Could not find recent data to generate a vibe check."
    articles_text = " ".join([f"{a['title']}. {a.get('description', '')}" for a in articles])
    context_text = " ".join(context)
    places_text = " | ".join(places)
    weather_text = f"The current temperature is {weather.get('temp')}°C with {weather.get('status')}."

    prompt = f"""
    Analyze the following data for {area}, Bangalore. Your output must be concise and use markdown formatting.
    Instructions:
    1.  Start with a one-sentence overall summary of the vibe.
    2.  Create a "Pulse Points" section with bullet points on traffic, safety, or events.
    3.  Create a "Top Spots" section with 2-3 bullet-point recommendations.
    4.  Create a "Weather & Attire" section with a brief clothing recommendation based on the weather.

    Data:
    - News: "{articles_text}"
    - Web Context: "{context_text}"
    - Local Places: "{places_text}"
    - Weather: "{weather_text}"
    """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e: return f"Error generating vibe check: {e}"

def save_search(email, area):
    try:
        history_collection.insert_one({"email": email, "area": area, "timestamp": datetime.utcnow()})
    except Exception as e: print(f"MongoDB Save Error: {e}")

def get_search_history(email):
    try:
        pipeline = [{"$match": {"email": email}}, {"$sort": {"timestamp": -1}}, {"$group": {"_id": "$area"}}, {"$limit": 5}]
        results = history_collection.aggregate(pipeline)
        return [doc["_id"] for doc in results]
    except Exception as e:
        print(f"MongoDB History Error: {e}")
        return []

# --- MAIN APP FUNCTION ---
def main():
    if 'token' not in st.session_state:
        st.title("Welcome to Bangalore Pulse 🔴")
        st.write("Please log in to continue.")
        result = oauth2.authorize_button(name="Login with Auth0", icon="https://auth0.com/favicon.ico", redirect_uri=AUTH0_REDIRECT_URI, scope="openid email profile", key="auth0")
        if result and "token" in result:
            st.session_state.token = result.get("token")
            st.rerun()
    else:
        token = st.session_state.get('token')
        user_info = jwt.decode(token['id_token'], options={"verify_signature": False})
        user_email = user_info.get('email')

        st.sidebar.title(f"Welcome, {user_info.get('name', 'User')}!")
        st.sidebar.write(user_email)
        if st.sidebar.button("Logout", key="logout_button"):
            del st.session_state.token
            st.rerun()
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Recent Searches")
        search_history = get_search_history(user_email)
        for item in search_history:
            if st.sidebar.button(item.title(), key=f"history_{item}"):
                st.session_state.area_input = item
                st.rerun()

        st.title("Bangalore Pulse 🔴")
        st.text("Get the real-time vibe of any neighborhood in Bangalore.")
        area_input = st.text_input("Search a neighborhood...", placeholder="e.g., Koramangala", label_visibility="collapsed", key="area_input").lower()

        if st.button("Get Pulse", key="pulse_button"):
            if area_input:
                with st.spinner(f"Taking the pulse of {area_input}..."):
                    news_results, context_results, place_results, weather_result = [], [], [], {}
                    
                    threads = [
                        threading.Thread(target=get_news_articles, args=(area_input, news_results)),
                        threading.Thread(target=get_contextual_data, args=(area_input, context_results)),
                        threading.Thread(target=get_local_places, args=(area_input, place_results)),
                        threading.Thread(target=get_weather, args=(area_input, weather_result))
                    ]
                    for t in threads: t.start()
                    for t in threads: t.join()

                    vibe_summary = get_gemini_vibe_check(news_results, context_results, place_results, weather_result, area_input)
                    save_search(user_email, area_input)
                    
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.subheader(f"Vibe Check: {area_input.title()}")
                        if weather_result:
                            st.metric("Current Temperature", f"{weather_result.get('temp', 'N/A')}°C", weather_result.get('status', ''))
                        st.markdown(vibe_summary)
                        if place_results:
                            st.subheader("📍 Top Rated Spots Nearby")
                            for place in place_results[:3]: st.info(place)
                    with col2:
                        st.subheader("Location")
                        coords = BANGALORE_COORDS.get(area_input)
                        if coords: st.map([{'lat': coords[0], 'lon': coords[1]}], zoom=13)
                        else: st.warning("Location not in quick-list.")
            else:
                st.warning("Please enter a neighborhood.")

# --- RUN THE APP ---
if __name__ == '__main__':
    main()