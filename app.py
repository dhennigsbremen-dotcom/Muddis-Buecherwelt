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
    
    /* Buttons generell */
    .stButton button {
        background-color: #d35400 !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 8px;
        border: none;
    }

    /* Spezielle Buttons (Löschen / Abbrechen) etwas dezenter oder anders */
    button[kind="secondary"] {
        background-color: #7f8c8d !important;
        color: white !important;
    }

    /* Tabs sehr groß */
    .stTabs [data-baseweb="tab"] {
        font-size: 1.5rem !important;
        padding: 15px !important;
        font-weight: 800 !important;
        color: #4a3b2a;
    }
    
    /* Eingabefelder */
    .stTextInput input, .stSelectbox div[data-baseweb="select"] {
        background-color: #fffaf0 !important;
        border: 1px solid #d35400 !important;
        color: #2c3e50 !important;
    }

    /* Buchstaben-Header für die Liste */
    .letter-header {
        font-size: 2.5rem;
        font-weight: 900;
        color: #e67e22;
        margin-top: 30px;
        margin-bottom: 10px;
        border-bottom: 3px solid #e67e22;
    }
    
    /* Design für einzelne Buch-Zeile in der Liste */
    .list-item-container {
        padding: 10px 0;
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
    if not raw_genre: return "Roman"
    if raw_genre in ["Roman", "Fiction", "Novel", "General", "Stories"]: return "Roman"
    if "Fantasy" in raw_genre: return "Fantasy"
    if "Thriller" in raw_genre or "Crime" in raw_genre: return "Krimi"
    try:
        translator = GoogleTranslator(source='auto', target='de')
        translated = translator.translate(raw_genre)
        if "römisch" in translated.lower(): return "Roman"
        return translated
    except: return "Roman"

def search_initial(user_query):
    result = search_google_books(user_query)
    if not result:
        result = search_open_library(user_query)
    if not result:
        return {"Titel": user_query, "Autor": "", "Genre": "Roman", "Cover": "", "Genre_Raw": "Roman"}
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

    # Session State initialisieren
    if "draft_book" not in st.session_state:
        st.session_state.draft_book = None
    if "search_step" not in st.session_state:
        st.session_state.search_step = 1 # 1 = Suchen, 2 = Prüfen

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
        
        # --- TAB 1: EINGABE (WIZARD MODUS) ---
        with tab1:
            # SCHRITT 1: NUR SUCHEN
            if st.session_state.search_step == 1:
                st.header("1. Welches Buch?")
                with st.form("search_form"):
                    col_search, col_btn = st.columns([3, 1])
                    with col_search:
                        search_query = st.text_input("Titel eingeben:", placeholder="z.B. Leon & Luise", label_visibility="collapsed")
                    with col_btn:
                        submitted_search = st.form_submit_button("🔍 Suchen")

                if submitted_search and search_query:
                    with st.spinner("Suche..."):
                        result = search_initial(search_query)
                        st.session_state.draft_book = result
                        # JETZT UMSCHALTEN AUF SCHRITT 2
                        st.session_state.search_step = 2
                        st.rerun()

            # SCHRITT 2: NUR PRÜFEN (Suchfeld ist weg!)
            elif st.session_state.search_step == 2 and st.session_state.draft_book:
                draft = st.session_state.draft_book
                
                # Kleiner Zurück-Button ganz oben
                if st.button("⬅️ Zurück / Anderes Buch suchen"):
                    st.session_state.search_step = 1
                    st.session_state.draft_book = None
                    st.rerun()

                st.markdown("---")
                st.header("2. Daten prüfen & ergänzen")
                
                # TITEL
                final_title = st.text_input("Titel:", value=draft["Titel"])
                
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
                    st.caption(f"Autor '{final_author}' übernommen.")

                final_rating = st.slider("Bewertung:", 1, 5, 5)
                
                # Großer Speicher-Button
                save_btn = st.button("💾 Speichern & Fertig", type="primary")
                
                if save_btn:
                    final_cover = draft["Cover"]
                    if final_author != draft["Autor"] and final_author.strip() != "":
                        with st.spinner("Suche Cover..."):
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
                        time.sleep(1.5)
                    else:
                        time.sleep(1)
                    
                    # ALLES ZURÜCKSETZEN FÜRS NÄCHSTE BUCH
                    st.session_state.draft_book = None
                    st.session_state.search_step = 1
                    st.rerun()

        # --- TAB 2: LISTE (MIT GRUPPIERUNG & MÜLLEIMER) ---
        with tab2:
            st.header("Deine Sammlung")
            
            if not df.empty:
                # Filter & Sortierung
                col_search, col_sort = st.columns([2, 1])
                with col_search:
                    search_filter = st.text_input("🔍 Liste durchsuchen:", placeholder="Titel oder Autor...")
                with col_sort:
                    sort_option = st.selectbox("Sortieren:", ["Neueste zuerst", "Titel (A-Z)", "Autor (A-Z)", "Beste Bewertung"])
                
                # 1. Filtern
                df_view = df.copy()
                if search_filter:
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(search_filter, case=False) | 
                        df_view["Autor"].astype(str).str.contains(search_filter, case=False)
                    ]
                
                # 2. Sortieren & Gruppierung vorbereiten
                use_grouping = False
                group_col = ""
                
                if sort_option == "Titel (A-Z)":
                    df_view = df_view.sort_values(by="Titel")
                    use_grouping = True
                    group_col = "Titel"
                elif sort_option == "Autor (A-Z)":
                    df_view = df_view.sort_values(by="Autor")
                    use_grouping = True
                    group_col = "Autor"
                elif sort_option == "Beste Bewertung":
                    df_view = df_view.sort_values(by="Bewertung", ascending=False)
                else: # Neueste zuerst
                    df_view = df_view.iloc[::-1]

                st.write(f"Zeige {len(df_view)} Bücher:")
                
                # --- LISTEN-ANZEIGE ---
                current_letter = None
                
                for index, row in df_view.iterrows():
                    # Gruppierungs-Header (A, B, C...)
                    if use_grouping:
                        # Ersten Buchstaben holen
                        val = str(row[group_col]).strip()
                        first_char = val[0].upper() if val else "?"
                        
                        if first_char != current_letter:
                            st.markdown(f'<div class="letter-header">{first_char}</div>', unsafe_allow_html=True)
                            current_letter = first_char

                    # Die Buch-Karte (Zeile)
                    with st.container(border=True):
                        # Layout: Bild | Infos | Mülleimer
                        c_img, c_info, c_del = st.columns([1, 4, 1])
                        
                        with c_img:
                            if row["Cover"]: st.image(row["Cover"], width=60)
                            else: st.write("📚")
                        
                        with c_info:
                            st.markdown(f"**{row['Titel']}**")
                            st.caption(f"{row['Autor']} | {row['Genre']}")
                            try: stars = "⭐" * int(float(row["Bewertung"]))
                            except: stars = ""
                            st.write(stars)
                            
                        with c_del:
                            # POPOVER: Klick öffnet ein Mini-Menü -> Sicherheit!
                            with st.popover("🗑️", help="Löschen"):
                                st.write("Wirklich löschen?")
                                # Wir nutzen einen Key, damit jeder Button einzigartig ist
                                if st.button("Ja, weg!", key=f"del_{index}"):
                                    with st.spinner("..."):
                                        try:
                                            # Wir suchen das Buch im Original-Sheet
                                            cell = worksheet.find(row["Titel"])
                                            worksheet.delete_rows(cell.row)
                                            st.toast("Buch gelöscht!") # Kleine Nachricht
                                            time.sleep(1)
                                            st.rerun()
                                        except:
                                            st.error("Fehler beim Finden.")

            else: st.info("Noch keine Bücher vorhanden.")

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
