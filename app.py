import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from deep_translator import GoogleTranslator
import time

# --- KONFIGURATION ---
st.set_page_config(page_title="Mamas Bibliothek", page_icon="📚", layout="centered")

# --- DESIGN (Optimiert für kleine Screens) ---
st.markdown("""
    <style>
    .stApp { background-color: #f5f5dc; }
    .stApp, .stMarkdown, p, div, label, h1, h2, h3, h4, span { color: #4a3b2a !important; }
    
    /* Buttons fett und gut drückbar */
    .stButton button {
        background-color: #d35400 !important;
        color: white !important;
        font-weight: bold !important;
        font-size: 18px !important;
        border-radius: 8px;
        padding: 15px !important; /* Mehr Padding für Touch */
        border: none;
        width: 100%;
        margin-top: 10px;
    }

    /* Tabs groß */
    .stTabs [data-baseweb="tab"] {
        font-size: 1.2rem !important;
        padding: 10px 5px !important;
        font-weight: 700 !important;
        color: #4a3b2a;
    }
    
    /* Eingabefelder */
    .stTextInput input {
        background-color: #fffaf0 !important;
        border: 2px solid #d35400 !important; /* Dickerer Rand */
        color: #2c3e50 !important;
        font-size: 16px !important; /* Größere Schrift zum Tippen */
    }
    
    /* Hinweise */
    .small-hint {
        font-size: 0.9rem;
        color: #7f8c8d !important;
        margin-bottom: 5px;
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

def setup_sheets(client):
    """Sorgt dafür, dass beide Tabellenblätter existieren"""
    sh = client.open("Mamas Bücherliste")
    
    # 1. Bücherliste (Sheet1)
    ws_books = sh.sheet1
    
    # 2. Autorenliste (Checken ob existiert, sonst erstellen)
    try:
        ws_authors = sh.worksheet("Autoren")
    except:
        ws_authors = sh.add_worksheet(title="Autoren", rows=1000, cols=1)
        ws_authors.update_cell(1, 1, "Name") # Header setzen
        
    return ws_books, ws_authors

def fetch_cover_background(titel, autor):
    """Sucht Cover, ändert aber KEINEN Text"""
    try:
        query = f"{titel} {autor}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=de&maxResults=1"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                return data["items"][0]["volumeInfo"].get("imageLinks", {}).get("thumbnail", "")
    except: return ""
    return ""

def get_smart_author_name(short_name, all_authors):
    """
    Der 'Twist': Prüft, ob 'Boyle' in 'Tom Coraghessan Boyle' steckt.
    Gibt den langen Namen zurück, wenn gefunden.
    """
    short_clean = short_name.strip().lower()
    if not short_clean: return short_name
    
    for full_name in all_authors:
        # Prüfen ob der eingegebene Schnipsel im vollen Namen steckt
        if short_clean in str(full_name).lower():
            return full_name # Treffer! Wir nehmen den langen Namen
            
    return short_name # Kein Treffer, wir nehmen was getippt wurde

# --- HAUPTPROGRAMM ---
def main():
    st.title("📚 Mamas Bücherwelt")

    try:
        client = get_connection()
        if client is None: st.stop()
        
        # Beide Tabellen laden
        ws_books, ws_authors = setup_sheets(client)
        
        # Autorenliste laden (für den Smart-Check)
        data_authors = ws_authors.get_all_records()
        df_authors = pd.DataFrame(data_authors)
        
        # Liste aller bekannten Autoren extrahieren
        known_authors_list = []
        if not df_authors.empty and "Name" in df_authors.columns:
            known_authors_list = [a for a in df_authors["Name"].tolist() if str(a).strip()]

        # Tabs
        tab1, tab2, tab3 = st.tabs(["✍️ Neu", "👥 Autoren", "🔍 Liste"])
        
        # --- TAB 1: SCHNELL-EINGABE (DAS KOMMA-FELD) ---
        with tab1:
            st.header("Buch eintragen")
            st.markdown('<div class="small-hint">Format: <b>Titel, Autor</b> (Komma ist wichtig!)</div>', unsafe_allow_html=True)
            
            # Das EINE Feld
            raw_input = st.text_input("Eingabe:", placeholder="z.B. Amerika, Boyle")
            
            # Bewertung direkt drunter
            rating = st.slider("Sterne:", 1, 5, 5)
            
            if st.button("💾 Speichern"):
                if "," in raw_input:
                    # 1. Splitten am Komma
                    parts = raw_input.split(",", 1) # Nur am ersten Komma teilen
                    titel_raw = parts[0].strip()
                    autor_fragment = parts[1].strip()
                    
                    if titel_raw and autor_fragment:
                        with st.spinner("Prüfe Autor & suche Cover..."):
                            # 2. Smart-Match: Den vollen Namen suchen
                            final_author = get_smart_author_name(autor_fragment, known_authors_list)
                            
                            # 3. Cover suchen (Heimlich)
                            cover_url = fetch_cover_background(titel_raw, final_author)
                            
                            # 4. Speichern in Bücherliste
                            ws_books.append_row([
                                titel_raw,
                                final_author,
                                "Roman", # Genre lassen wir simpel
                                rating,
                                cover_url
                            ])
                            
                            # 5. Falls der Autor GANZ neu war (Input == Output), fragen wir nicht, 
                            # sondern speichern ihn NICHT automatisch in die Masterliste. 
                            # Das soll sie lieber bewusst im Autoren-Tab machen, um Müll zu vermeiden.
                        
                        st.success(f"Gespeichert!\nTitel: {titel_raw}\nAutor: {final_author}")
                        if final_author != autor_fragment:
                            st.info(f"ℹ️ Habe den Autor '{autor_fragment}' zu '{final_author}' vervollständigt!")
                        
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("Bitte Titel UND Autor eingeben.")
                else:
                    st.error("⚠️ Das Komma fehlt! Bitte 'Titel, Autor' eingeben.")

        # --- TAB 2: AUTOREN VERWALTUNG (DER TWIST) ---
        with tab2:
            st.header("Autoren-Verzeichnis")
            st.info("Hier kannst du Autoren mit vollem Namen eintragen. Wenn du später Bücher einträgst, reicht der Nachname.")
            
            # Einfache Tabelle zum Bearbeiten
            # Wir nutzen data_editor, damit sie Namen korrigieren oder neue Zeilen anfügen kann
            
            if df_authors.empty:
                # Leeres DataFrame erstellen, falls Sheet leer
                df_authors = pd.DataFrame({"Name": [""]})

            edited_authors = st.data_editor(
                df_authors,
                num_rows="dynamic", # Erlaubt Hinzufügen unten
                use_container_width=True,
                column_config={
                    "Name": st.column_config.TextColumn("Autorenname (Vollständig)", required=True)
                },
                hide_index=True
            )
            
            # Button zum Speichern der Änderungen an der Autorenliste
            if st.button("👥 Autorenliste aktualisieren"):
                # Umwandeln in Liste von Listen für GSpread
                # Leerzeilen filtern
                clean_data = edited_authors[edited_authors["Name"].astype(str).str.strip() != ""]
                
                # Sheet leeren und neu schreiben (einfachste Methode um Sync zu halten)
                ws_authors.clear()
                ws_authors.update_cell(1, 1, "Name") # Header wieder rein
                if not clean_data.empty:
                    ws_authors.update([clean_data.columns.values.tolist()] + clean_data.values.tolist())
                
                st.success("Autorenliste gespeichert!")
                time.sleep(1)
                st.rerun()

        # --- TAB 3: BÜCHERLISTE (Clean) ---
        with tab3:
            st.header("Sammlung")
            
            # Daten laden
            data_books = ws_books.get_all_records()
            df_books = pd.DataFrame()
            if data_books:
                df_books = pd.DataFrame(data_books)
                # Spalten sicherstellen
                for c in ["Titel", "Autor", "Bewertung", "Cover"]: 
                    if c not in df_books.columns: df_books[c] = ""
            
            if not df_books.empty:
                df_books["Löschen"] = False
                
                # Suche
                search = st.text_input("🔍 Suchen:", placeholder="Titel...", label_visibility="collapsed")
                
                df_view = df_books.copy()
                if search:
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(search, case=False) |
                        df_view["Autor"].astype(str).str.contains(search, case=False)
                    ]
                
                # Anzeige
                with st.form("list_view"):
                    edited_df = st.data_editor(
                        df_view,
                        column_order=["Titel", "Autor", "Bewertung", "Cover", "Löschen"],
                        column_config={
                            "Löschen": st.column_config.CheckboxColumn("X", width="small", default=False),
                            "Cover": st.column_config.ImageColumn("Img", width="small"),
                            "Titel": st.column_config.TextColumn("Titel", disabled=True),
                            "Autor": st.column_config.TextColumn("Autor", disabled=True),
                            "Bewertung": st.column_config.NumberColumn("⭐", disabled=True)
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    if st.form_submit_button("🗑️ Löschen"):
                        to_delete = edited_df[edited_df["Löschen"]==True]
                        if not to_delete.empty:
                            for index, row in to_delete.iterrows():
                                try:
                                    cell = ws_books.find(row["Titel"])
                                    ws_books.delete_rows(cell.row)
                                except: pass
                            st.success("Gelöscht!")
                            time.sleep(1)
                            st.rerun()
            else:
                st.info("Liste leer.")

    except Exception as e: st.error(f"Fehler: {e}")

if __name__ == "__main__":
    main()
