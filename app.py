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
    div[data-testid="stForm"] button {
        background-color: #d35400 !important;
        color: white !important;
        font-weight: bold !important;
        font-size: 18px !important;
        border: none;
        border-radius: 8px;
        padding: 15px !important;
        width: 100%;
    }
    
    /* Tabellen-Design Anpassungen */
    div[data-testid="stDataFrame"] {
        background-color: white;
        padding: 10px;
        border-radius: 10px;
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
    """Suche via Google Books (Nur Metadaten)"""
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=de&maxResults=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                return {
                    "Autor": ", ".join(info.get("authors", ["Unbekannt"])),
                    "Cover": info.get("imageLinks", {}).get("thumbnail", ""),
                    "Genre_Raw": info.get("categories", ["Roman"])[0]
                }
        return None
    except: return None

def search_open_library(query):
    """Suche via OpenLibrary (Nur Metadaten)"""
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
                return {"Autor": autor, "Cover": cover, "Genre_Raw": genre}
        return None
    except: return None

def search_and_process_book(user_title):
    """
    SICHERE SUCHE: 
    Der Titel wird NICHT mehr von der Datenbank überschrieben.
    Wir suchen nur nach Autor, Cover und Genre.
    """
    
    # Standardwerte (Titel ist fix das, was eingegeben wurde!)
    book_data = {
        "Titel": user_title, 
        "Autor": "Unbekannt",
        "Genre": "Roman",
        "Cover": ""
    }
    
    # Wir suchen trotzdem, um Lücken zu füllen
    result = search_google_books(user_title)
    if not result:
        result = search_open_library(user_title)
    
    if result:
        # Wir übernehmen NUR das Beiwerk, niemals den Titel
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
            # Spaltenbereinigung
            rename_map = {}
            if "Cover_Link" in df.columns: rename_map["Cover_Link"] = "Cover"
            if "Bild" in df.columns: rename_map["Bild"] = "Cover"
            if "Sterne" in df.columns: rename_map["Sterne"] = "Bewertung"
            if "Stars" in df.columns: rename_map["Stars"] = "Bewertung"
            if rename_map: df = df.rename(columns=rename_map)
            for col in ["Cover", "Bewertung", "Titel", "Autor", "Genre"]:
                if col not in df.columns: df[col] = "" if col != "Bewertung" else 0

        tab1, tab2, tab3 = st.tabs(["📖 Neues Buch", "🔍 Meine Liste", "📊 Statistik"])
        
        # --- TAB 1: EINGABE ---
        with tab1:
            st.header("Neues Buch eintragen")
            with st.form("quick_add_form", clear_on_submit=True):
                st.caption("Der Titel wird genau so gespeichert, wie du ihn hier eintippst.")
                title_input = st.text_input("Titel:", placeholder="z.B. Leon & Luise")
                rating = st.slider("Bewertung:", 1, 5, 5)
                submitted = st.form_submit_button("💾 SPEICHERN & SUCHEN")
                
                if submitted and title_input:
                    with st.spinner("Suche Cover & Autor..."):
                        # Neue Logik: Titel bleibt fest!
                        book_info = search_and_process_book(title_input)
                        
                        worksheet.append_row([
                            book_info["Titel"],
                            book_info["Autor"],
                            book_info["Genre"],
                            rating,
                            book_info["Cover"]
                        ])
                        
                        st.success(f"Gespeichert: {book_info['Titel']}")

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
                        else:
                            time.sleep(1)
                        st.rerun()

        # --- TAB 2: MEINE LISTE (TABELLEN-VERSION) ---
        with tab2:
            st.header("Deine Sammlung")
            
            if not df.empty:
                # 1. LÖSCHEN (Bleibt wie es ist, weil es gut funktioniert)
                with st.expander("🗑 Bücher löschen"):
                    all_titles = df["Titel"].tolist()
                    delete_list = st.multiselect("Welche Bücher sollen weg?", all_titles)
                    
                    if delete_list:
                        if st.button(f"Löschen ({len(delete_list)})"):
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

                # 2. FILTERN (Einfaches Suchfeld über der Tabelle)
                search_filter = st.text_input("🔍 Schnell-Filter (Titel oder Autor):", placeholder="Tippe zum Filtern...")

                # Daten filtern, falls was eingetippt wurde
                df_view = df.copy()
                if search_filter:
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(search_filter, case=False) | 
                        df_view["Autor"].astype(str).str.contains(search_filter, case=False)
                    ]

                # 3. DIE SCHÖNE TABELLE
                # Wir nutzen st.dataframe mit "column_config", um Bilder und Sterne anzuzeigen
                st.dataframe(
                    df_view,
                    column_config={
                        "Cover": st.column_config.ImageColumn(
                            "Cover", 
                            help="Buchcover",
                            width="small" # Macht das Bild schön kompakt
                        ),
                        "Titel": st.column_config.TextColumn(
                            "Titel",
                            width="medium"
                        ),
                        "Autor": st.column_config.TextColumn(
                            "Autor",
                            width="medium"
                        ),
                        "Genre": st.column_config.TextColumn(
                            "Genre",
                            width="small"
                        ),
                        "Bewertung": st.column_config.NumberColumn(
                            "Sterne",
                            help="Deine Bewertung (1-5)",
                            format="%d ⭐", # Zeigt Zahl + Stern an
                            width="small"
                        )
                    },
                    use_container_width=True, # Nutzt die volle Breite
                    hide_index=True # Versteckt die Zeilennummern (0, 1, 2...)
                )
                
                st.caption("💡 Tipp: Klicke auf die Spalten-Namen (z.B. 'Titel'), um die Liste zu sortieren.")

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
