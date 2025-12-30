import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import time

# --- KONFIGURATION ---
st.set_page_config(page_title="Mamas Bibliothek", page_icon="📚", layout="centered")

# --- DESIGN (iPhone SE optimiert: GROSSE TABS) ---
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
        padding: 15px !important;
        border: none;
        width: 100%;
        margin-top: 10px;
    }

    /* --- TAB DESIGN: GROSS & GETRENNT --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px; /* Lücke zwischen den Tabs */
    }

    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #eaddcf;
        border-radius: 8px;
        padding: 0px 10px !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        color: #4a3b2a;
        border: 1px solid #d35400;
        flex-grow: 1;
    }

    .stTabs [aria-selected="true"] {
        background-color: #d35400 !important;
        color: white !important;
    }
    
    /* Eingabefelder */
    .stTextInput input {
        background-color: #fffaf0 !important;
        border: 2px solid #d35400 !important;
        color: #2c3e50 !important;
        font-size: 16px !important;
    }
    
    /* Hinweise */
    .small-hint {
        font-size: 1.0rem;
        color: #d35400 !important; /* Warnfarbe Orange */
        font-weight: bold;
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
    sh = client.open("Mamas Bücherliste")
    ws_books = sh.sheet1
    try:
        ws_authors = sh.worksheet("Autoren")
    except:
        ws_authors = sh.add_worksheet(title="Autoren", rows=1000, cols=1)
        ws_authors.update_cell(1, 1, "Name")
    return ws_books, ws_authors

def sync_authors(ws_books, ws_authors):
    # 1. Alle Bücher holen
    books_data = ws_books.get_all_records()
    if not books_data: return 0
    
    # Autoren aus Büchern extrahieren
    book_authors = set()
    for row in books_data:
        if "Autor" in row and str(row["Autor"]).strip():
            book_authors.add(str(row["Autor"]).strip())
            
    # 2. Bestehende Autorenliste holen
    auth_data = ws_authors.get_all_records()
    existing_authors = set()
    for row in auth_data:
        if "Name" in row and str(row["Name"]).strip():
            existing_authors.add(str(row["Name"]).strip())
            
    # 3. Was fehlt?
    missing = list(book_authors - existing_authors)
    missing.sort()
    
    # 4. Nachtragen
    if missing:
        rows_to_add = [[name] for name in missing]
        ws_authors.append_rows(rows_to_add)
        return len(missing)
    return 0

def fetch_cover_background(titel, autor):
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
    short_clean = short_name.strip().lower()
    if not short_clean: return short_name
    for full_name in all_authors:
        if short_clean in str(full_name).lower():
            return full_name 
    return short_name 

# --- HAUPTPROGRAMM ---
def main():
    st.title("📚 Mamas Bücherwelt")

    try:
        client = get_connection()
        if client is None: st.stop()
        
        # 1. Verbindung & Auto-Sync
        ws_books, ws_authors = setup_sheets(client)
        added_count = sync_authors(ws_books, ws_authors)
        if added_count > 0:
            st.toast(f"✅ {added_count} Autoren synchronisiert!", icon="🧙‍♀️")

        # 2. Daten laden
        data_authors = ws_authors.get_all_records()
        df_authors = pd.DataFrame(data_authors)
        
        known_authors_list = []
        if not df_authors.empty and "Name" in df_authors.columns:
            known_authors_list = [a for a in df_authors["Name"].tolist() if str(a).strip()]

        # Tabs (Kachel-Design)
        tab1, tab2, tab3 = st.tabs(["✍️ Neu", "👥 Autoren", "🔍 Liste"])
        
        # --- TAB 1: EINGABE ---
        with tab1:
            st.header("Buch eintragen")
            
            # HIER IST DER NEUE HINWEIS
            st.markdown('<div class="small-hint">Eingeben: Titel, Autor<br>(das Komma ist wichtig!!!)</div>', unsafe_allow_html=True)
            
            # HIER IST DAS NEUE PLACEHOLDER
            raw_input = st.text_input("Eingabe:", placeholder="Titel, Autor")
            
            rating = st.slider("Sterne:", 1, 5, 5)
            
            if st.button("💾 Speichern"):
                if "," in raw_input:
                    parts = raw_input.split(",", 1)
                    titel_raw = parts[0].strip()
                    autor_fragment = parts[1].strip()
                    
                    if titel_raw and autor_fragment:
                        with st.spinner("..."):
                            final_author = get_smart_author_name(autor_fragment, known_authors_list)
                            cover_url = fetch_cover_background(titel_raw, final_author)
                            
                            ws_books.append_row([
                                titel_raw,
                                final_author,
                                "Roman", 
                                rating,
                                cover_url
                            ])
                        
                        st.success(f"Gespeichert!\n{titel_raw} ({final_author})")
                        if final_author != autor_fragment:
                            st.caption(f"Autor vervollständigt zu: {final_author}")
                        
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error("Text fehlt.")
                else:
                    st.error("⚠️ Komma vergessen! Bitte 'Titel, Autor' eingeben.")

        # --- TAB 2: AUTOREN ---
        with tab2:
            st.header("Autoren-Liste")
            
            data_books_for_count = ws_books.get_all_records()
            df_books_count = pd.DataFrame(data_books_for_count)
            
            author_counts = {}
            if not df_books_count.empty and "Autor" in df_books_count.columns:
                author_counts = df_books_count["Autor"].value_counts().to_dict()

            if df_authors.empty:
                df_authors = pd.DataFrame({"Name": [""]})

            df_authors["Anzahl Bücher"] = df_authors["Name"].map(author_counts).fillna(0).astype(int)

            edited_authors = st.data_editor(
                df_authors,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Name": st.column_config.TextColumn("Name (Vollständig)", required=True),
                    "Anzahl Bücher": st.column_config.NumberColumn("Bücher", disabled=True)
                },
                hide_index=True
            )
            
            if st.button("👥 Liste aktualisieren"):
                clean_data = edited_authors[edited_authors["Name"].astype(str).str.strip() != ""]
                df_to_save = clean_data[["Name"]]
                
                ws_authors.clear()
                ws_authors.update_cell(1, 1, "Name")
                if not df_to_save.empty:
                    ws_authors.update([df_to_save.columns.values.tolist()] + df_to_save.values.tolist())
                
                st.success("Gespeichert!")
                time.sleep(1)
                st.rerun()

        # --- TAB 3: BÜCHERLISTE ---
        with tab3:
            st.header("Sammlung")
            
            data_books = ws_books.get_all_records()
            df_books = pd.DataFrame()
            if data_books:
                df_books = pd.DataFrame(data_books)
                for c in ["Titel", "Autor", "Bewertung", "Cover"]: 
                    if c not in df_books.columns: df_books[c] = ""
            
            if not df_books.empty:
                df_books["Löschen"] = False
                
                search = st.text_input("🔍 Suchen:", placeholder="Titel...", label_visibility="collapsed")
                
                df_view = df_books.copy()
                if search:
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(search, case=False) |
                        df_view["Autor"].astype(str).str.contains(search, case=False)
                    ]
                
                with st.form("list_view"):
                    edited_df = st.data_editor(
                        df_view,
                        column_order=["Löschen", "Titel", "Autor", "Bewertung", "Cover"],
                        column_config={
                            "Löschen": st.column_config.CheckboxColumn("Weg?", width="small", default=False),
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
                st.info("Leer.")

    except Exception as e: st.error(f"Fehler: {e}")

if __name__ == "__main__":
    main()
