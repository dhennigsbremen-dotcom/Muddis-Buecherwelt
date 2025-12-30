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
    
    /* Buttons */
    .stButton button {
        background-color: #d35400 !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 8px;
        border: none;
        width: 100%;
        padding: 10px;
    }

    /* Tabs groß & lesbar */
    .stTabs [data-baseweb="tab"] {
        font-size: 1.5rem !important;
        padding: 15px !important;
        font-weight: 800 !important;
        color: #4a3b2a;
    }
    
    /* Tabelle hübsch machen */
    div[data-testid="stDataFrame"] {
        background-color: white;
        padding: 10px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    
    /* Eingabefelder */
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

def fetch_background_info(titel, autor):
    """
    Sucht im HINTERGRUND nach Cover & Genre.
    Ändert aber niemals den Titel oder Autor!
    """
    try:
        query = f"{titel} {autor}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=de&maxResults=1"
        response = requests.get(url)
        
        cover = ""
        genre = "Roman" # Standardwert
        
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                
                # 1. Cover holen
                cover = info.get("imageLinks", {}).get("thumbnail", "")
                
                # 2. Genre versuchen zu holen & zu übersetzen
                raw_genre = info.get("categories", ["Roman"])[0]
                genre = process_genre(raw_genre)
                
        return cover, genre
    except:
        return "", "Roman"

def process_genre(raw_genre):
    """Übersetzt Genres sauber"""
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

def get_lastname(full_name):
    """Hilfsfunktion: Holt das letzte Wort als Nachnamen für die Sortierung"""
    if not isinstance(full_name, str) or not full_name.strip():
        return ""
    return full_name.strip().split(" ")[-1]

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
                # Autorenliste bereinigen und sortieren
                existing_authors = sorted(list(set([a for a in df["Autor"].astype(str).tolist() if a.strip()])))

        tab1, tab2, tab3 = st.tabs(["📖 Neues Buch", "🔍 Meine Liste", "📊 Statistik"])
        
        # --- TAB 1: EINGABE (SIMPEL & MANUELL) ---
        with tab1:
            st.header("Neues Buch eintragen")
            
            # WICHTIG: Wir nutzen KEIN st.form um die Eingabefelder herum,
            # damit das "Neuer Autor"-Feld sofort auftaucht, wenn man es auswählt.
            
            # 1. Titel
            title_input = st.text_input("Buchtitel:", placeholder="z.B. Die unendliche Geschichte")
            
            # 2. Autor Auswahl
            select_options = ["(Bitte wählen...)"] + existing_authors + ["➕ Neuer Autor hinzufügen"]
            author_choice = st.selectbox("Autor:", options=select_options)
            
            # Logik für den Autoren-Namen
            final_author_name = ""
            
            # 3. Autor manuell (erscheint nur bei Bedarf)
            if author_choice == "➕ Neuer Autor hinzufügen":
                final_author_name = st.text_input("Neuen Autorennamen eingeben:", placeholder="Vorname Nachname")
            elif author_choice != "(Bitte wählen...)":
                final_author_name = author_choice

            # 4. Bewertung
            rating = st.slider("Bewertung:", 1, 5, 5)
            
            st.write("") # Abstand
            
            # SPEICHER-BUTTON
            if st.button("💾 Buch speichern", type="primary"):
                # Validierung
                if not title_input:
                    st.error("Bitte gib einen Titel ein!")
                elif not final_author_name:
                    st.error("Bitte wähle einen Autor oder gib einen neuen ein!")
                else:
                    # Alles okay -> Speichern!
                    with st.spinner("Speichere... (Suche Cover im Hintergrund)"):
                        # Cover & Genre holen wir uns automatisch
                        found_cover, found_genre = fetch_background_info(title_input, final_author_name)
                        
                        worksheet.append_row([
                            title_input,        # Dein Titel (Exakt!)
                            final_author_name,  # Dein Autor (Exakt!)
                            found_genre,        # Genre (Automatisch)
                            rating,
                            found_cover         # Cover (Automatisch)
                        ])
                    
                    st.success(f"Gespeichert: {title_input}")
                    
                    if show_animation:
                        st.balloons()
                        time.sleep(1.5)
                    else:
                        time.sleep(1)
                    
                    st.rerun()

        # --- TAB 2: LISTE ---
        with tab2:
            st.header("Deine Sammlung")
            
            if not df.empty:
                df["Löschen"] = False
                
                # Filter & Sortierung
                col_search, col_sort = st.columns([2, 1])
                with col_search:
                    search_filter = st.text_input("🔍 Liste durchsuchen:", placeholder="Titel oder Autor...")
                with col_sort:
                    sort_option = st.selectbox("Sortieren:", 
                                               ["Autor (A-Z)", "Titel (A-Z)", "Neueste zuerst", "Beste Bewertung"],
                                               index=0)
                
                df_view = df.copy()
                if search_filter:
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(search_filter, case=False) | 
                        df_view["Autor"].astype(str).str.contains(search_filter, case=False)
                    ]
                
                # Sortier-Logik (Nachname)
                if sort_option == "Autor (A-Z)":
                    df_view["_Nachname"] = df_view["Autor"].apply(get_lastname)
                    df_view = df_view.sort_values(by="_Nachname")
                elif sort_option == "Titel (A-Z)":
                    df_view = df_view.sort_values(by="Titel")
                elif sort_option == "Beste Bewertung":
                    df_view = df_view.sort_values(by="Bewertung", ascending=False)
                else: 
                    df_view = df_view.iloc[::-1]

                st.write(f"Zeige {len(df_view)} Bücher:")
                
                # LISTE IM FORMULAR (damit es nicht flackert beim Anhaken)
                with st.form("list_form"):
                    cols = ["Titel", "Autor", "Genre", "Bewertung", "Cover", "Löschen"]
                    
                    edited_df = st.data_editor(
                        df_view,
                        column_order=cols,
                        column_config={
                            "Löschen": st.column_config.CheckboxColumn("Weg?", default=False, width="small"),
                            "Cover": st.column_config.ImageColumn("Bild", width="small"),
                            "Titel": st.column_config.TextColumn("Titel", width="medium", disabled=True),
                            "Autor": st.column_config.TextColumn("Autor", width="medium", disabled=True),
                            "Genre": st.column_config.TextColumn("Genre", width="small", disabled=True),
                            "Bewertung": st.column_config.NumberColumn("⭐", format="%d", width="small", disabled=True)
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    st.write("")
                    delete_btn = st.form_submit_button("💾 Änderungen anwenden / Löschen ausführen", type="primary")
                    
                    if delete_btn:
                        rows_to_delete = edited_df[edited_df["Löschen"] == True]
                        if not rows_to_delete.empty:
                            with st.spinner(f"Lösche {len(rows_to_delete)} Buch/Bücher..."):
                                for index, row in rows_to_delete.iterrows():
                                    try:
                                        cell = worksheet.find(row["Titel"])
                                        worksheet.delete_rows(cell.row)
                                        time.sleep(0.5)
                                    except: pass
                                st.success("Erfolgreich gelöscht!")
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.info("Keine Bücher zum Löschen markiert.")
                
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
            else: st.write("Keine Daten.")

    except Exception as e: st.error(f"Fehler: {e}")

if __name__ == "__main__":
    main()
