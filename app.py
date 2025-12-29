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
    
    /* Buttons stylen */
    .stButton button {
        background-color: #d35400 !important;
        color: white !important;
        font-weight: bold !important;
        font-size: 16px !important;
        border-radius: 8px;
        padding: 10px 20px !important;
        border: none;
    }
    
    /* Tabellen-Design */
    div[data-testid="stDataFrame"] {
        background-color: white;
        padding: 10px;
        border-radius: 10px;
    }
    
    /* Vorschau Box beim Suchen */
    .preview-box {
        background-color: #fffaf0;
        border: 2px solid #d35400;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNKTIONEN ---

@st.cache_resource
def get_connection():
    """Verbindet zu Google Sheets"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        try:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        except FileNotFoundError:
            st.error("Weder Secrets noch credentials.json gefunden!")
            return None
            
    client = gspread.authorize(creds)
    return client

def search_google_books(query):
    """Suche via Google Books"""
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=de&maxResults=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                return {
                    "Titel": info.get("title", query), # Google Titel oft genauer
                    "Autor": ", ".join(info.get("authors", ["Unbekannt"])),
                    "Cover": info.get("imageLinks", {}).get("thumbnail", ""),
                    "Genre_Raw": info.get("categories", ["Roman"])[0]
                }
        return None
    except: return None

def search_open_library(query):
    """Suche via OpenLibrary"""
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
                return {
                    "Titel": item.get("title", query),
                    "Autor": autor, 
                    "Cover": cover, 
                    "Genre_Raw": genre
                }
        return None
    except: return None

def search_book_info(user_query):
    """Hybrid-Suche"""
    # 1. Google
    result = search_google_books(user_query)
    # 2. OpenLibrary Backup
    if not result:
        result = search_open_library(user_query)
    
    # Aufbereitung
    book_data = {
        "Titel": user_query, # Fallback
        "Autor": "Unbekannt",
        "Genre": "Roman",
        "Cover": ""
    }

    if result:
        book_data["Titel"] = result["Titel"]
        book_data["Autor"] = result["Autor"]
        book_data["Cover"] = result["Cover"]
        try:
            translator = GoogleTranslator(source='auto', target='de')
            book_data["Genre"] = translator.translate(result["Genre_Raw"])
        except:
            book_data["Genre"] = result["Genre_Raw"]
            
    return book_data

# --- HAUPTPROGRAMM ---
def main():
    st.title("📚 Mamas Bücherwelt")

    if "found_book" not in st.session_state:
        st.session_state.found_book = None

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

        tab1, tab2, tab3 = st.tabs(["📖 Neues Buch", "🔍 Meine Liste", "📊 Statistik"])
        
        # --- TAB 1: EINGABE (Zwei-Schritt-Verfahren) ---
        with tab1:
            st.header("1. Buch suchen")
            
            # Suchfeld (Ohne Formular, damit wir das Ergebnis direkt anzeigen können)
            col_in, col_btn = st.columns([3, 1])
            with col_in:
                search_query = st.text_input("Titel eingeben:", placeholder="z.B. Leon & Luise", key="search_input")
            with col_btn:
                st.write("") # Abstand
                st.write("") 
                search_clicked = st.button("🔍 Suchen")

            # Logik: Wenn gesucht wird
            if search_clicked and search_query:
                with st.spinner("Suche in Datenbank..."):
                    result = search_book_info(search_query)
                    st.session_state.found_book = result
            
            st.markdown("---")

            # ANZEIGE & SPEICHERN
            if st.session_state.found_book:
                book = st.session_state.found_book
                
                st.header("2. Gefundenes Buch prüfen")
                
                with st.container():
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        if book["Cover"]:
                            st.image(book["Cover"], width=100)
                        else:
                            st.write("📚 (Kein Bild)")
                    with c2:
                        st.subheader(book["Titel"])
                        st.write(f"**Autor:** {book['Autor']}")
                        st.write(f"**Genre:** {book['Genre']}")
                
                st.info("Ist das das richtige Buch? Wenn nicht, ändere den Suchtext oben (z.B. Autor hinzufügen).")

                # Speicher-Formular
                with st.form("save_form"):
                    rating = st.slider("Deine Bewertung:", 1, 5, 5)
                    save_btn = st.form_submit_button("💾 Ja, dieses Buch speichern")
                    
                    if save_btn:
                        worksheet.append_row([
                            book["Titel"],
                            book["Autor"],
                            book["Genre"],
                            rating,
                            book["Cover"]
                        ])
                        
                        st.success(f"Gespeichert: {book['Titel']}")
                        
                        if show_animation:
                            st.markdown("""
                                <style>
                                @keyframes flyBook {
                                    0%   { transform: translate(-10vw, 100vh) rotate(0deg) scale(0.5); opacity: 0; }
                                    10%  { opacity: 1; }
                                    90%  { opacity: 1; }
                                    100% { transform: translate(110vw, -50vh) rotate(360deg) scale(1.5); opacity: 0; }
                                }
                                .flying-book-container {
                                    position: fixed;
                                    bottom: 0; left: 0; width: 100vw; height: 100vh;
                                    pointer-events: none; z-index: 9999;
                                }
                                .the-book {
                                    position: absolute;
                                    font-size: 6rem;
                                    animation: flyBook 3s ease-in-out forwards;
                                }
                                </style>
                                <div class="flying-book-container"><div class="the-book">📖</div></div>
                            """, unsafe_allow_html=True)
                            time.sleep(3.5)
                        
                        # Reset
                        st.session_state.found_book = None
                        st.rerun()

        # --- TAB 2: MEINE LISTE ---
        with tab2:
            st.header("Deine Sammlung")
            
            if not df.empty:
                # 1. LÖSCHEN (Jetzt im Formular -> Kein Refresh beim Auswählen!)
                with st.expander("🗑 Bücher löschen"):
                    with st.form("delete_form"):
                        st.write("Wähle Bücher zum Löschen (Seite lädt erst nach Klick auf 'Löschen' neu):")
                        all_titles = df["Titel"].tolist()
                        delete_list = st.multiselect("Bücher auswählen:", all_titles)
                        
                        delete_submitted = st.form_submit_button("Endgültig löschen")
                        
                        if delete_submitted and delete_list:
                            with st.spinner("Lösche..."):
                                rows_to_delete = []
                                for title in delete_list:
                                    try:
                                        cell = worksheet.find(title)
                                        rows_to_delete.append(cell.row)
                                    except: pass
                                
                                rows_to_delete = sorted(list(set(rows_to_delete)), reverse=True)
                                for row_num in rows_to_delete:
                                    worksheet.delete_rows(row_num)
                                    time.sleep(0.5)
                                st.success("Gelöscht!")
                                time.sleep(1)
                                st.rerun()

                st.markdown("---")

                # 2. FILTER & TABELLE
                search_filter = st.text_input("🔍 Schnell-Filter:", placeholder="Tippe zum Filtern...")

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
            else:
                st.info("Noch keine Bücher vorhanden.")

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
            else:
                st.write("Keine Daten.")

    except Exception as e:
        st.error(f"Ein Fehler ist aufgetreten: {e}")

if __name__ == "__main__":
    main()
