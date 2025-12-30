import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import time
from deep_translator import GoogleTranslator

# --- KONFIGURATION ---
st.set_page_config(page_title="Mamas Bibliothek", page_icon="📚", layout="centered")

# --- DESIGN (iPhone SE optimiert) ---
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

    /* --- TAB DESIGN --- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
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
        color: #d35400 !important;
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
    books_data = ws_books.get_all_records()
    if not books_data: return 0
    
    book_authors = set()
    for row in books_data:
        if "Autor" in row and str(row["Autor"]).strip():
            book_authors.add(str(row["Autor"]).strip())
            
    auth_data = ws_authors.get_all_records()
    existing_authors = set()
    for row in auth_data:
        if "Name" in row and str(row["Name"]).strip():
            existing_authors.add(str(row["Name"]).strip())
            
    missing = list(book_authors - existing_authors)
    missing.sort()
    
    if missing:
        rows_to_add = [[name] for name in missing]
        ws_authors.append_rows(rows_to_add)
        return len(missing)
    return 0

def process_genre(raw_genre):
    """Verhindert 'römisch' und übersetzt sauber"""
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

def fetch_book_data_background(titel, autor):
    """
    Sucht Cover UND Genre im Hintergrund.
    Gibt (Cover-URL, Genre) zurück.
    """
    try:
        query = f"{titel} {autor}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=de&maxResults=1"
        response = requests.get(url)
        
        cover = ""
        genre = "Roman" # Fallback
        
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                # Cover
                cover = info.get("imageLinks", {}).get("thumbnail", "")
                # Genre
                raw_cat = info.get("categories", ["Roman"])[0]
                genre = process_genre(raw_cat)
                
        return cover, genre
    except:
        return "", "Roman"

def get_smart_author_name(short_name, all_authors):
    short_clean = short_name.strip().lower()
    if not short_clean: return short_name
    for full_name in all_authors:
        if short_clean in str(full_name).lower():
            return full_name 
    return short_name 

def get_lastname(full_name):
    if not isinstance(full_name, str) or not full_name.strip():
        return ""
    return full_name.strip().split(" ")[-1].lower()

# --- HAUPTPROGRAMM ---
def main():
    st.title("📚 Mamas Bücherwelt")

    if "input_key" not in st.session_state:
        st.session_state.input_key = 0

    try:
        client = get_connection()
        if client is None: st.stop()
        
        ws_books, ws_authors = setup_sheets(client)
        added_count = sync_authors(ws_books, ws_authors)
        if added_count > 0:
            st.toast(f"✅ {added_count} Autoren synchronisiert!", icon="🧙‍♀️")

        data_authors = ws_authors.get_all_records()
        df_authors = pd.DataFrame(data_authors)
        known_authors_list = []
        if not df_authors.empty and "Name" in df_authors.columns:
            known_authors_list = [a for a in df_authors["Name"].tolist() if str(a).strip()]

        tab1, tab2, tab3 = st.tabs(["✍️ Neu", "👥 Autoren", "🔍 Liste"])
        
        # --- TAB 1: EINGABE ---
        with tab1:
            st.header("Buch eintragen")
            st.markdown('<div class="small-hint">Eingeben: Titel, Autor<br>(das Komma ist wichtig!!!)</div>', unsafe_allow_html=True)
            
            raw_input = st.text_input(
                "Eingabe:", 
                placeholder="Titel, Autor", 
                key=f"book_input_{st.session_state.input_key}"
            )
            
            rating = st.slider("Sterne:", 1, 5, 5)
            
            if st.button("💾 Speichern"):
                if "," in raw_input:
                    parts = raw_input.split(",", 1)
                    titel_raw = parts[0].strip()
                    autor_fragment = parts[1].strip()
                    
                    if titel_raw and autor_fragment:
                        with st.spinner("Speichere & suche Infos im Hintergrund..."):
                            # Smart Author
                            final_author = get_smart_author_name(autor_fragment, known_authors_list)
                            # Cover & Genre holen
                            fetched_cover, fetched_genre = fetch_book_data_background(titel_raw, final_author)
                            
                            ws_books.append_row([
                                titel_raw,
                                final_author,
                                fetched_genre, 
                                rating,
                                fetched_cover
                            ])
                        
                        st.success(f"Gespeichert!\n{titel_raw}\n({fetched_genre})")
                        if final_author != autor_fragment:
                            st.caption(f"Autor vervollständigt: {final_author}")
                        
                        st.balloons()
                        st.session_state.input_key += 1
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
                    "Name": st.column_config.TextColumn("Name", required=True),
                    "Anzahl Bücher": st.column_config.NumberColumn("Anzahl", disabled=True)
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
                for c in ["Titel", "Autor", "Bewertung", "Cover", "Genre"]: 
                    if c not in df_books.columns: df_books[c] = ""
            
            if not df_books.empty:
                df_books["Löschen"] = False
                
                search = st.text_input("🔍 Suchen:", placeholder="Titel...", label_visibility="collapsed")
                
                # --- SORTIERUNG: IMMER NACH NACHNAME ---
                df_books["_Nachname"] = df_books["Autor"].apply(get_lastname)
                df_view = df_books.sort_values(by="_Nachname")
                
                if search:
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(search, case=False) |
                        df_view["Autor"].astype(str).str.contains(search, case=False)
                    ]
                
                with st.form("list_view"):
                    # SPALTEN: Löschen links, Bild dabei
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

                st.markdown("---")
                
                # --- REPARATUR-BEREICH FÜR ALTE BÜCHER ---
                with st.expander("🔧 Wartung & fehlende Cover"):
                    st.write("Klicke hier, wenn Bücher kein Bild haben. Das Programm sucht sie dann nachträglich.")
                    if st.button("🔄 Fehlende Bilder & Genres nachtragen"):
                        updates_made = 0
                        with st.status("Durchsuche Bibliothek...", expanded=True) as status:
                            # Wir iterieren durch ALLE Bücher in der Original-DB (nicht im View)
                            # GSpread ist 1-basiert. Header ist Zeile 1. Daten ab Zeile 2.
                            all_values = ws_books.get_all_values()
                            # Header: Titel(0), Autor(1), Genre(2), Sterne(3), Cover(4) -> check indices!
                            headers = all_values[0]
                            
                            # Indices finden
                            try:
                                idx_titel = headers.index("Titel")
                                idx_autor = headers.index("Autor")
                                idx_cover = headers.index("Cover")
                                idx_genre = headers.index("Genre")
                            except:
                                st.error("Spaltenstruktur passt nicht. Bitte 'Titel', 'Autor', 'Cover', 'Genre' prüfen.")
                                st.stop()

                            for i, row in enumerate(all_values[1:], start=2): # Start bei Zeile 2
                                current_cover = row[idx_cover] if len(row) > idx_cover else ""
                                current_genre = row[idx_genre] if len(row) > idx_genre else ""
                                
                                # Wenn Cover leer ist -> Suchen!
                                if not current_cover:
                                    titel = row[idx_titel]
                                    autor = row[idx_autor]
                                    
                                    st.write(f"Suche Infos für: {titel}...")
                                    new_cover, new_genre = fetch_book_data_background(titel, autor)
                                    
                                    if new_cover:
                                        # Update Cover (Spalte ist idx_cover + 1 wegen 1-based indexing)
                                        ws_books.update_cell(i, idx_cover + 1, new_cover)
                                        updates_made += 1
                                    
                                    # Update Genre falls leer oder "Roman" (wir versuchen es genauer)
                                    if (not current_genre or current_genre == "Roman") and new_genre != "Roman":
                                        ws_books.update_cell(i, idx_genre + 1, new_genre)
                                    
                                    time.sleep(1.0) # Pause gegen Google Sperre

                            status.update(label="Fertig!", state="complete", expanded=False)
                        
                        if updates_made > 0:
                            st.success(f"{updates_made} Cover nachgetragen!")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.info("Alle Bücher haben bereits Bilder (oder Google hat nichts gefunden).")

            else:
                st.info("Leer.")

    except Exception as e: st.error(f"Fehler: {e}")

if __name__ == "__main__":
    main()
