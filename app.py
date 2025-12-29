import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from deep_translator import GoogleTranslator
import time

# --- KONFIGURATION ---
st.set_page_config(page_title="Mamas Bibliothek", page_icon="📚", layout="centered")

# --- DESIGN ---
st.markdown("""
    <style>
    .stApp { background-color: #f5f5dc; }
    .stApp, .stMarkdown, p, div, label, h1, h2, h3, h4, span { color: #4a3b2a !important; }
    
    .stButton button {
        background-color: #d35400 !important;
        color: white !important;
        font-weight: bold !important;
        font-size: 18px !important;
        border-radius: 8px;
        padding: 12px 20px !important;
        border: none;
        width: 100%;
    }
    
    .stTabs [data-baseweb="tab"] {
        font-size: 1.5rem !important;
        padding: 15px !important;
        font-weight: 800 !important;
        color: #4a3b2a;
    }
    
    div[data-testid="stDataFrame"] {
        background-color: white;
        padding: 10px;
        border-radius: 10px;
    }
    
    .stTextInput input, .stSelectbox div[data-baseweb="select"] {
        background-color: #fffaf0 !important;
        border: 1px solid #d35400 !important;
        color: #2c3e50 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNKTIONEN ---

@st.cache_resource
def get_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        try:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        except FileNotFoundError: return None
    return gspread.authorize(creds)

def search_google_books(query):
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=de&maxResults=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                return {
                    "Titel": info.get("title", query),
                    "Autor": ", ".join(info.get("authors", ["Unbekannt"])),
                    "Cover": info.get("imageLinks", {}).get("thumbnail", ""),
                    "Genre_Raw": info.get("categories", ["Roman"])[0]
                }
    except: return None
    return None

def search_open_library(query):
    try:
        clean_query = query.replace(" ", "+")
        url = f"https://openlibrary.org/search.json?q={clean_query}&language=ger&limit=1"
        headers = {"User-Agent": "MamasBuecherweltApp/1.0"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("numFound", 0) > 0 and len(data.get("docs", [])) > 0:
                item = data["docs"][0]
                cover = f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-M.jpg" if item.get("cover_i") else ""
                autor = item.get("author_name")[0] if item.get("author_name") else "Unbekannt"
                genre = item.get("subject")[0] if item.get("subject") else "Roman"
                return {"Titel": item.get("title", query), "Autor": autor, "Cover": cover, "Genre_Raw": genre}
    except: return None
    return None

def process_genre(raw_genre):
    """Verhindert, dass aus Roman 'römisch' wird"""
    if not raw_genre: return "Roman"
    
    # 1. Direkte Treffer abfangen (bevor der Übersetzer Quatsch macht)
    if raw_genre in ["Roman", "Fiction", "Novel", "General", "Stories"]:
        return "Roman"
    if "Fantasy" in raw_genre: return "Fantasy"
    if "Thriller" in raw_genre or "Crime" in raw_genre: return "Krimi"
    
    # 2. Übersetzen
    try:
        translator = GoogleTranslator(source='auto', target='de')
        translated = translator.translate(raw_genre)
        # 3. Notbremse für Übersetzungsfehler
        if "römisch" in translated.lower(): return "Roman"
        return translated
    except:
        return "Roman"

def search_initial(user_query):
    result = search_google_books(user_query)
    if not result:
        result = search_open_library(user_query)
    
    if not result:
        return {"Titel": user_query, "Autor": "", "Genre": "Roman", "Cover": "", "Genre_Raw": "Roman"}
    
    # Genre bereinigen
    result["Genre"] = process_genre(result.get("Genre_Raw", "Roman"))
    
    return result

def check_cover_update(titel, autor):
    try:
        query = f"{titel} {autor}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                return data["items"][0]["volumeInfo"].get("imageLinks", {}).get("thumbnail", "")
    except: return ""
    return ""

# --- HAUPTPROGRAMM ---
def main():
    st.title("📚 Mamas Bücherwelt")

    if "draft_book" not in st.session_state:
        st.session_state.draft_book = None
    if "last_search" not in st.session_state:
        st.session_state.last_search = ""

    with st.sidebar:
        st.header("Einstellungen")
        show_animation = st.checkbox("🎉 Animationen aktivieren", value=True)
    
    try:
        client = get_connection()
        if client is None: st.stop()
        sheet_name = "Mamas Bücherliste"
        sh = client.open(sheet_name)
        worksheet = sh.sheet1
        
        # Daten laden
        data = worksheet.get_all_records()
        df = pd.DataFrame()
        existing_authors = []
        if data:
            df = pd.DataFrame(data)
            rename_map = {}
            if "Cover_Link" in df.columns: rename_map["Cover_Link"] = "Cover"
            if "Bild" in df.columns: rename_map["Bild"] = "Cover"
            if "Sterne" in df.columns: rename_map["Sterne"] = "Bewertung"
            if "Stars" in df.columns: rename_map["Stars"] = "Bewertung"
            if rename_map: df = df.rename(columns=rename_map)
            for col in ["Cover", "Bewertung", "Titel", "Autor", "Genre"]:
                if col not in df.columns: df[col] = "" if col != "Bewertung" else 0
            if "Autor" in df.columns:
                existing_authors = sorted(list(set([a for a in df["Autor"].astype(str).tolist() if a.strip()])))

        tab1, tab2, tab3 = st.tabs(["📖 Neues Buch", "🔍 Meine Liste", "📊 Statistik"])
        
        # --- TAB 1: EINGABE ---
        with tab1:
            st.header("1. Buch suchen")
            with st.form("search_form"):
                col_search, col_btn = st.columns([3, 1])
                with col_search:
                    search_query = st.text_input("Titel:", placeholder="z.B. Harry Potter und der Stein der Weisen", label_visibility="collapsed")
                with col_btn:
                    submitted_search = st.form_submit_button("🔍 Suchen")

            if submitted_search and search_query:
                st.session_state.last_search = search_query # Eingabe merken
                with st.spinner("Suche..."):
                    result = search_initial(search_query)
                    st.session_state.draft_book = result
            
            st.markdown("---")

            # SCHRITT 2
            if st.session_state.draft_book:
                draft = st.session_state.draft_book
                
                st.header("2. Daten prüfen & ergänzen")
                
                c_img, c_form = st.columns([1, 2])
                with c_img:
                    if draft["Cover"]: st.image(draft["Cover"], width=120)
                    else: st.write("📚 (Kein Bild)")
                
                with c_form:
                    # TITEL: Hier nehmen wir jetzt standardmäßig DEINE Sucheingabe!
                    # Wir ignorieren den englischen Titel der API, außer du änderst es selbst.
                    user_input_title = st.session_state.last_search if st.session_state.last_search else draft["Titel"]
                    final_title = st.text_input("Titel:", value=user_input_title)
                    
                    # AUTOR
                    found_author = draft["Autor"]
                    select_options = ["➕ Neuer Autor / Manuelle Eingabe"] + existing_authors
                    default_index = 0
                    if found_author in existing_authors:
                        default_index = select_options.index(found_author)
                    
                    selected_option = st.selectbox("Autor auswählen:", options=select_options, index=default_index)
                    
                    if selected_option == "➕ Neuer Autor / Manuelle Eingabe":
                        final_author = st.text_input("Autor eintippen:", value=found_author)
                    else:
                        final_author = selected_option
                        # Kleiner Hinweis, damit man weiß, dass es geklappt hat
                        st.caption(f"Autor '{final_author}' übernommen.")

                    final_rating = st.slider("Bewertung:", 1, 5, 5)
                    save_btn = st.button("💾 In Liste speichern")
                    
                    if save_btn:
                        # Cover aktualisieren falls Autor geändert
                        final_cover = draft["Cover"]
                        if final_author != draft["Autor"] and final_author.strip() != "":
                            with st.spinner("Autor geändert... suche passendes Cover..."):
                                new_cover = check_cover_update(final_title, final_author)
                                if new_cover: final_cover = new_cover

                        worksheet.append_row([
                            final_title,
                            final_author,
                            draft["Genre"], 
                            final_rating,
                            final_cover
                        ])
                        
                        st.success(f"Gespeichert: {final_title}")
                        if show_animation:
                            st.balloons()
                            time.sleep(2)
                        else:
                            time.sleep(1)
                        st.session_state.draft_book = None
                        st.rerun()

        # --- TAB 2: LISTE ---
        with tab2:
            st.header("Deine Sammlung")
            if not df.empty:
                with st.expander("🗑 Bücher löschen"):
                    with st.form("delete_form"):
                        delete_list = st.multiselect("Löschen:", df["Titel"].tolist())
                        if st.form_submit_button("Löschen") and delete_list:
                            with st.spinner("Lösche..."):
                                for title in delete_list:
                                    try: worksheet.delete_rows(worksheet.find(title).row)
                                    except: pass
                                    time.sleep(0.5)
                                st.success("Weg damit!")
                                time.sleep(1)
                                st.rerun()
                st.markdown("---")
                search_filter = st.text_input("🔍 Filter:", placeholder="Tippe zum Filtern...")
                df_view = df.copy()
                if search_filter:
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(search_filter, case=False) | 
                        df_view["Autor"].astype(str).str.contains(search_filter, case=False)
                    ]
                st.dataframe(
                    df_view,
                    column_config={
                        "Cover": st.column_config.ImageColumn("Cover", width="small"),
                        "Titel": st.column_config.TextColumn("Titel", width="medium"),
                        "Autor": st.column_config.TextColumn("Autor", width="medium"),
                        "Genre": st.column_config.TextColumn("Genre", width="small"),
                        "Bewertung": st.column_config.NumberColumn("Sterne", format="%d ⭐", width="small")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else: st.info("Leer.")

        # --- TAB 3: STATISTIK ---
        with tab3:
            st.header("Überblick")
            if not df.empty:
                c1, c2, c3 = st.columns(3)
                c1.metric("Anzahl", len(df))
                if "Autor" in df.columns and not df["Autor"].empty: c2.metric("Top Autor", df["Autor"].mode()[0])
                if "Genre" in df.columns and not df["Genre"].empty: c3.metric("Top Genre", df["Genre"].mode()[0])
                st.markdown("---")
                total = len(df)
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.subheader("Nach Genre")
                    if "Genre" in df.columns:
                        for g, c in df["Genre"].value_counts().items():
                            if g:
                                st.write(f"**{g}**: {c}")
                                st.progress(min(int((c/total)*100)/100, 1.0))
                with sc2:
                    st.subheader("Top Autoren")
                    if "Autor" in df.columns:
                        for a, c in df["Autor"].value_counts().head(5).items():
                            if a:
                                st.write(f"**{a}**: {c}")
                                st.progress(min(int((c/total)*100)/100, 1.0))
            else: st.write("Keine Daten.")

    except Exception as e: st.error(f"Fehler: {e}")

if __name__ == "__main__":
    main()
