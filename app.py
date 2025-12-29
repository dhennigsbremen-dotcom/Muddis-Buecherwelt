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
        font-size: 18px !important;
        border-radius: 8px;
        padding: 12px 20px !important;
        border: none;
        width: 100%;
    }
    
    /* TABS GRÖSSER MACHEN (Wunsch erfüllt!) */
    .stTabs [data-baseweb="tab"] {
        font-size: 1.5rem; /* Schriftgröße */
        padding: 15px;      /* Abstand */
        font-weight: bold;
    }
    
    /* Tabellen-Design */
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

def search_cover_only(titel, autor):
    """
    Sucht NUR nach einem Cover-Bild im Hintergrund.
    Ändert keine Texte!
    """
    try:
        # Wir suchen nach "Titel Autor" für bessere Treffer
        query = f"{titel} {autor}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                # Wir geben nur das Bild zurück, sonst nichts
                return info.get("imageLinks", {}).get("thumbnail", "")
    except:
        return ""
    return ""

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
        
        # 1. DATEN VORHER LADEN (Damit wir die Autoren kennen)
        data = worksheet.get_all_records()
        df = pd.DataFrame()
        existing_authors = []
        
        if data:
            df = pd.DataFrame(data)
            # Spaltenbereinigung
            rename_map = {}
            if "Cover_Link" in df.columns: rename_map["Cover_Link"] = "Cover"
            if "Bild" in df.columns: rename_map["Bild"] = "Cover"
            if "Sterne" in df.columns: rename_map["Sterne"] = "Bewertung"
            if "Stars" in df.columns: rename_map["Stars"] = "Bewertung"
            if rename_map: df = df.rename(columns=rename_map)
            
            # Fehlende Spalten ergänzen
            for col in ["Cover", "Bewertung", "Titel", "Autor", "Genre"]:
                if col not in df.columns: df[col] = "" if col != "Bewertung" else 0
            
            # Autorenliste erstellen (alphabetisch sortiert, ohne Duplikate)
            if "Autor" in df.columns:
                raw_authors = df["Autor"].unique().tolist()
                # Leere Einträge entfernen und sortieren
                existing_authors = sorted([a for a in raw_authors if str(a).strip() != ""])

        # TABS ERSTELLEN
        tab1, tab2, tab3 = st.tabs(["📖 Neues Buch", "🔍 Meine Liste", "📊 Statistik"])
        
        # --- TAB 1: EINGABE (MANUELL & SICHER) ---
        with tab1:
            st.header("Buch manuell eintragen")
            
            with st.form("manual_add_form", clear_on_submit=True):
                # 1. TITEL
                title_input = st.text_input("Titel:", placeholder="z.B. Leon & Luise")
                
                # 2. AUTOR (Auswahl oder Neu)
                # Wir fügen "(Neuer Autor)" ganz oben in die Liste ein
                select_options = ["(Neuer Autor eintragen)"] + existing_authors
                author_select = st.selectbox("Autor auswählen:", select_options)
                
                # Wenn "(Neuer Autor)" gewählt ist, zeigen wir ein Textfeld (wird unten ausgewertet)
                new_author_input = st.text_input("...oder neuen Autor eintippen:", 
                                                 placeholder="z.B. Alex Capus",
                                                 help="Nur ausfüllen, wenn oben '(Neuer Autor)' gewählt ist.")
                
                # 3. BEWERTUNG
                rating = st.slider("Bewertung:", 1, 5, 5)
                
                # SPEICHERN BUTTON
                submitted = st.form_submit_button("💾 Buch jetzt speichern")
                
                if submitted:
                    # Validierung: Titel muss da sein
                    if not title_input:
                        st.error("Bitte gib mindestens einen Titel ein!")
                    else:
                        # Welcher Autor wird genommen?
                        final_author = "Unbekannt"
                        if author_select == "(Neuer Autor eintragen)":
                            if new_author_input:
                                final_author = new_author_input
                        else:
                            final_author = author_select
                        
                        # Wir versuchen im Hintergrund, ein Cover zu finden
                        # Aber wir ändern NICHT den Titel oder Autor!
                        with st.spinner("Speichere... (Suche Cover...)"):
                            found_cover = search_cover_only(title_input, final_author)
                            
                            # Ab in die Tabelle
                            worksheet.append_row([
                                title_input,    # Dein Titel (Exakt!)
                                final_author,   # Dein Autor (Exakt!)
                                "Roman",        # Standard-Genre (manuell zu viel Arbeit)
                                rating,
                                found_cover
                            ])
                        
                        st.success(f"Gespeichert: {title_input} von {final_author}")
                        
                        # Animation
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

        # --- TAB 2: MEINE LISTE ---
        with tab2:
            st.header("Deine Sammlung")
            
            if not df.empty:
                # LÖSCHEN (Formular-basiert, wie gewünscht)
                with st.expander("🗑 Bücher löschen"):
                    with st.form("delete_form"):
                        st.write("Wähle Bücher zum Löschen:")
                        all_titles = df["Titel"].tolist()
                        # Multiselect für einfaches Auswählen
                        delete_list = st.multiselect("Auswahl:", all_titles)
                        
                        delete_submitted = st.form_submit_button("Ausgewählte löschen")
                        
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

                # Filter
                search_filter = st.text_input("🔍 Filter (Titel/Autor):", placeholder="Tippe zum Filtern...")

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
