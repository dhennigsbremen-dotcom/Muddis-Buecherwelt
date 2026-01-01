import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import time
from deep_translator import GoogleTranslator

# --- KONFIGURATION ---
st.set_page_config(page_title="Mamas Bibliothek", page_icon="📚", layout="centered")

# --- KONSTANTEN ---
NO_COVER_MARKER = "-" 

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
        font-size: 18px !important;
        border-radius: 8px;
        padding: 15px !important;
        border: none;
        width: 100%;
        margin-top: 10px;
    }

    /* NAVIGATION */
    div[role="radiogroup"] {
        display: flex;
        flex-direction: row;
        justify-content: space-between;
        gap: 10px;
        width: 100%;
    }
    
    div[role="radiogroup"] label {
        background-color: #eaddcf !important;
        border: 1px solid #d35400;
        border-radius: 8px;
        padding: 10px;
        flex-grow: 1;
        text-align: center;
        justify-content: center;
        font-weight: bold;
        color: #4a3b2a;
    }

    /* Eingabefelder */
    .stTextInput input {
        background-color: #fffaf0 !important;
        border: 2px solid #d35400 !important;
        color: #2c3e50 !important;
        font-size: 16px !important;
    }
    
    .small-hint {
        font-size: 1.0rem;
        color: #d35400 !important;
        font-weight: bold;
        margin-bottom: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNKTIONEN ---

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

def fetch_data_from_sheet(worksheet):
    try:
        all_values = worksheet.get_all_values()
        if len(all_values) < 2: return pd.DataFrame()
        
        headers = [str(h).strip().lower() for h in all_values[0]]
        col_map = {}
        for idx, h in enumerate(headers):
            if "titel" in h: col_map["Titel"] = idx
            elif "autor" in h: col_map["Autor"] = idx
            elif h in ["cover", "bild", "image", "img"]: col_map["Cover"] = idx
            elif h in ["sterne", "bewertung", "rating"]: col_map["Bewertung"] = idx
            elif h in ["genre", "kategorie"]: col_map["Genre"] = idx
            elif "name" in h: col_map["Name"] = idx

        rows = []
        for raw_row in all_values[1:]:
            entry = {"Titel": "", "Autor": "", "Cover": "", "Bewertung": "", "Genre": "", "Name": ""}
            for key, idx in col_map.items():
                if idx < len(raw_row):
                    entry[key] = raw_row[idx]
            if entry["Titel"] or entry["Name"]:
                rows.append(entry)
        return pd.DataFrame(rows)
    except Exception as e:
        return pd.DataFrame()

def force_reload():
    if "df_books" in st.session_state: del st.session_state.df_books
    if "df_authors" in st.session_state: del st.session_state.df_authors
    st.rerun()

def sync_authors(ws_books, ws_authors):
    if "sync_done" in st.session_state: return 0
    if "df_books" not in st.session_state: st.session_state.df_books = fetch_data_from_sheet(ws_books)
    if "df_authors" not in st.session_state: st.session_state.df_authors = fetch_data_from_sheet(ws_authors)
        
    df_b = st.session_state.df_books
    df_a = st.session_state.df_authors
    if df_b.empty: return 0
    
    # Hier trimmen wir schon mal beim Einlesen
    book_authors = set([a.strip() for a in df_b["Autor"].tolist() if a.strip()])
    existing_authors = set([a.strip() for a in df_a["Name"].tolist() if a.strip()]) if not df_a.empty and "Name" in df_a else set()
    
    missing = list(book_authors - existing_authors)
    missing.sort()
    
    if missing:
        rows_to_add = [[name] for name in missing]
        ws_authors.append_rows(rows_to_add)
        st.session_state.sync_done = True
        del st.session_state.df_authors
        return len(missing)
    st.session_state.sync_done = True
    return 0

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

# --- SUCHE ---
def search_open_library_cover(titel, autor):
    try:
        query = f"{titel} {autor}".replace(" ", "+")
        url = f"https://openlibrary.org/search.json?q={query}&limit=1"
        headers = {"User-Agent": "MamasBuecherweltApp/1.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("numFound", 0) > 0 and len(data.get("docs", [])) > 0:
                item = data["docs"][0]
                if item.get("cover_i"):
                    return f"https://covers.openlibrary.org/b/id/{item.get('cover_i')}-M.jpg"
    except: return ""
    return ""

def fetch_book_data_background(titel, autor):
    cover = ""
    genre = "Roman"
    try:
        query = f"{titel} {autor}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&langRestrict=de&maxResults=1"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                cover = info.get("imageLinks", {}).get("thumbnail", "")
                raw_cat = info.get("categories", ["Roman"])[0]
                genre = process_genre(raw_cat)
    except: pass

    if not cover:
        try:
            ol_cover = search_open_library_cover(titel, autor)
            if ol_cover: cover = ol_cover
        except: pass

    return cover, genre

def get_smart_author_name(short_name, all_authors):
    short_clean = short_name.strip().lower()
    if not short_clean: return short_name
    sorted_authors = sorted(all_authors, key=len, reverse=True)
    for full_name in sorted_authors:
        if short_clean in str(full_name).lower():
            return full_name 
    return short_name 

def get_lastname(full_name):
    if not isinstance(full_name, str) or not full_name.strip(): return ""
    return full_name.strip().split(" ")[-1].lower()

def silent_background_check(ws_books, df_books):
    if df_books.empty: return 0
    if "Cover" not in df_books.columns: return 0
    missing = df_books[ (df_books["Cover"] == "") | (df_books["Cover"].isnull()) ]
    missing = missing[ missing["Cover"] != NO_COVER_MARKER ]
    if not missing.empty:
        to_check = missing.head(3)
        updates = 0
        all_vals = ws_books.get_all_values()
        headers = [str(h).lower() for h in all_vals[0]]
        idx_t = -1; idx_a = -1; idx_c = -1
        for i, h in enumerate(headers):
            if "titel" in h: idx_t = i
            if "autor" in h: idx_a = i
            if h in ["cover", "bild", "image", "img"]: idx_c = i
        if idx_c == -1 or idx_t == -1: return 0
        for idx, row in to_check.iterrows():
            tit = row["Titel"]
            aut = row["Autor"]
            nc, ng = fetch_book_data_background(tit, aut)
            try:
                cell = ws_books.find(tit)
                if nc:
                    ws_books.update_cell(cell.row, idx_c + 1, nc)
                    updates += 1
                else:
                    ws_books.update_cell(cell.row, idx_c + 1, NO_COVER_MARKER)
                time.sleep(1)
            except: pass
        return updates
    return 0

# --- DUBLETTEN KILLER 3.0 (Nukleare Option) ---
def cleanup_author_duplicates(ws_books, ws_authors, df_authors):
    """
    1. Normalisiert alle Namen (entfernt unsichtbare Zeichen).
    2. Mergt Kurzformen (Berkel -> Christian Berkel).
    3. Schreibt die Autorenliste KOMPLETT neu (nur Unique values).
    """
    
    # Hilfsfunktion zum Säubern: Entfernt auch "Non-breaking spaces" (\xa0)
    def deep_clean(text):
        return str(text).replace(u'\xa0', ' ').strip()

    all_raw_authors = [deep_clean(a) for a in df_authors["Name"].tolist() if str(a).strip()]
    
    # 1. Clustering: Wir gruppieren gleiche Namen (case-insensitive)
    # Ziel: Wenn "Christine Brand" und "christine brand" da sind, nehmen wir die schönere Variante.
    canonical_names = {} # lower_case -> Display Name
    
    for name in all_raw_authors:
        lower = name.lower()
        if lower not in canonical_names:
            canonical_names[lower] = name
        else:
            # Wenn wir schon einen haben, nehmen wir den längeren (falls es z.B. "Brand" vs "Brandt" wäre - hier eher Groß/Klein)
            # Bevorzugt: Der mit Großbuchstaben
            current = canonical_names[lower]
            if name[0].isupper() and not current[0].isupper():
                canonical_names[lower] = name

    # 2. Kurzform-Check (Berkel -> Christian Berkel)
    # Wir arbeiten jetzt nur noch mit den "sauberen" Keys
    unique_keys = list(canonical_names.keys())
    unique_keys.sort(key=len, reverse=True) # Längste zuerst

    replacements = {} # lower_bad -> Display_Good

    for i, long_key in enumerate(unique_keys):
        for short_key in unique_keys[i+1:]:
            # Prüfen ob short in long steckt
            if short_key in long_key and short_key != long_key:
                # Mergen!
                target_display = canonical_names[long_key]
                replacements[short_key] = target_display
                # Auch den Display-Namen des kurzen Keys auf das Ziel mappen
                # (Damit wir später in der DB aufräumen können)
                replacements[canonical_names[short_key].lower()] = target_display

    # Jetzt haben wir 'replacements'. Alles was NICHT in replacements ist, ist ein gültiger Autor.
    final_unique_authors = set()
    for lower_key, display_name in canonical_names.items():
        if lower_key not in replacements:
            final_unique_authors.add(display_name)
        else:
            # Es ist ein ersetzter Name -> wir fügen das ZIEL hinzu
            final_unique_authors.add(replacements[lower_key])

    # 3. Update BÜCHER Sheet (Namen korrigieren)
    # Wir müssen durch ALLE Bücher gehen und schauen, ob der Autor "schmutzig" ist
    books_vals = ws_books.get_all_values()
    headers = [str(h).lower() for h in books_vals[0]]
    idx_a = -1
    for i, h in enumerate(headers):
        if "autor" in h: idx_a = i
    
    updates_count = 0
    if idx_a != -1:
        for i, row in enumerate(books_vals[1:], start=2):
            if len(row) > idx_a:
                original_auth = row[idx_a]
                clean_auth = deep_clean(original_auth)
                lower_auth = clean_auth.lower()
                
                new_val = None
                
                # Fall A: Es ist eine Kurzform, die ersetzt werden muss
                if lower_auth in replacements:
                    new_val = replacements[lower_auth]
                
                # Fall B: Es ist keine Kurzform, aber vielleicht war die Schreibweise "unsauber"
                # (z.B. unsichtbares Leerzeichen). Wir holen den 'kanonischen' Namen.
                elif lower_auth in canonical_names:
                    # Wenn der Name in der Zelle anders aussieht als unser sauberes Ziel
                    if original_auth != canonical_names[lower_auth]:
                        new_val = canonical_names[lower_auth]

                if new_val and new_val != original_auth:
                    ws_books.update_cell(i, idx_a + 1, new_val)
                    updates_count += 1
                    time.sleep(0.5)

    # 4. Update AUTOREN Sheet (Komplett neu schreiben)
    ws_authors.clear()
    ws_authors.update_cell(1, 1, "Name")
    
    sorted_list = sorted(list(final_unique_authors))
    rows_to_write = [[name] for name in sorted_list]
    
    if rows_to_write:
        ws_authors.update(values=[["Name"]] + rows_to_write)

    return updates_count + 1 # +1 damit User Feedback bekommt, auch wenn nur Liste bereinigt wurde

# --- HAUPTPROGRAMM ---
def main():
    st.title("📚 Mamas Bücherwelt")

    if "input_key" not in st.session_state: st.session_state.input_key = 0
    if "background_check_done" not in st.session_state: st.session_state.background_check_done = False

    try:
        client = get_connection()
        if client is None: st.stop()
        ws_books, ws_authors = setup_sheets(client)

        if "df_books" not in st.session_state:
            with st.spinner("Lade Bücherregal..."):
                st.session_state.df_books = fetch_data_from_sheet(ws_books)
        
        if "df_authors" not in st.session_state:
            st.session_state.df_authors = fetch_data_from_sheet(ws_authors)

        added = sync_authors(ws_books, ws_authors)
        if added > 0: st.toast(f"✅ {added} Autoren synchronisiert!")

        if not st.session_state.background_check_done:
            updates = silent_background_check(ws_books, st.session_state.df_books)
            st.session_state.background_check_done = True
            if updates > 0:
                st.toast(f"✨ Habe {updates} fehlende Bilder nachgeladen!", icon="🕵️‍♂️")

        known_authors_list = []
        if not st.session_state.df_authors.empty:
            known_authors_list = [a for a in st.session_state.df_authors["Name"].tolist() if str(a).strip()]

        selected_nav = st.radio(
            "Navigation", 
            ["✍️ Neu", "👥 Autoren", "🔍 Liste"], 
            horizontal=True,
            label_visibility="collapsed"
        )
        
        # --- TAB 1: EINGABE ---
        if selected_nav == "✍️ Neu":
            st.header("Buch eintragen")
            st.markdown('<div class="small-hint">Eingeben: Titel, Autor<br>(das Komma ist wichtig!!!)</div>', unsafe_allow_html=True)
            
            with st.form("new_book_form", clear_on_submit=False):
                raw_input = st.text_input("Eingabe:", placeholder="Titel, Autor", key=f"inp_{st.session_state.input_key}")
                rating = st.slider("Sterne:", 1, 5, 5)
                submitted = st.form_submit_button("💾 Speichern")
            
            if submitted:
                if "," in raw_input:
                    parts = raw_input.split(",", 1)
                    titel = parts[0].strip()
                    autor_frag = parts[1].strip()
                    if titel and autor_frag:
                        with st.spinner("Speichere & suche Cover..."):
                            final_author = get_smart_author_name(autor_frag, known_authors_list)
                            c, g = fetch_book_data_background(titel, final_author)
                            final_cover = c if c else NO_COVER_MARKER
                            ws_books.append_row([titel, final_author, g, rating, final_cover])
                            del st.session_state.df_books
                        st.success(f"Gespeichert: {titel}")
                        if final_author != autor_frag: st.info(f"Autor vervollständigt: {final_author}")
                        st.balloons() 
                        time.sleep(2) 
                        st.session_state.input_key += 1
                        st.rerun()
                    else: st.error("Text fehlt.")
                else: st.error("⚠️ Komma vergessen!")

        # --- TAB 2: AUTOREN ---
        elif selected_nav == "👥 Autoren":
            st.header("Autoren")
            
            # --- 1. MANUELL HINZUFÜGEN (JETZT OFFEN) ---
            st.caption("Einen neuen Autorennamen vorbereiten:")
            with st.form("add_auth_form"):
                col_inp, col_btn = st.columns([3, 1])
                with col_inp:
                    new_auth_name = st.text_input("Name:", label_visibility="collapsed", placeholder="Name eingeben...")
                with col_btn:
                    add_btn = st.form_submit_button("Hinzufügen")
                
                if add_btn and new_auth_name:
                    if new_auth_name not in known_authors_list:
                        ws_authors.append_row([new_auth_name])
                        del st.session_state.df_authors
                        st.success(f"'{new_auth_name}' dabei!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.warning("Gibt's schon.")

            st.markdown("---")

            # --- 2. EDITOR ---
            df_b = st.session_state.df_books
            df_a = st.session_state.df_authors.copy()
            counts = {}
            if not df_b.empty: counts = df_b["Autor"].value_counts().to_dict()
            if df_a.empty: df_a = pd.DataFrame({"Name": [""]})
            
            df_a["Anzahl d. Bücher"] = df_a["Name"].map(counts).fillna(0).astype(int)

            total_books = len(df_b)
            st.metric("Bücher insgesamt:", total_books)

            df_a["_Nachname"] = df_a["Name"].apply(get_lastname)
            df_a = df_a.sort_values(by="_Nachname")

            df_display = df_a[["Name", "Anzahl d. Bücher"]].reset_index(drop=True)

            edited_authors = st.data_editor(
                df_display,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Name": st.column_config.TextColumn("Name", required=True),
                    "Anzahl d. Bücher": st.column_config.NumberColumn("Anzahl d. Bücher", disabled=True)
                },
                hide_index=True
            )
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Liste speichern"):
                    clean = edited_authors[edited_authors["Name"].astype(str).str.strip() != ""]
                    df_save = clean[["Name"]]
                    ws_authors.clear()
                    ws_authors.update_cell(1, 1, "Name")
                    if not df_save.empty: ws_authors.update([df_save.columns.values.tolist()] + df_save.values.tolist())
                    del st.session_state.df_authors
                    st.success("Gespeichert!")
                    st.rerun()
            
            with c2:
                if st.button("🧹 Autoren aufräumen"):
                    with st.spinner("Wasche Namen & entferne Dubletten (Hard Reset)..."):
                        merged_count = cleanup_author_duplicates(ws_books, ws_authors, df_a)
                        del st.session_state.df_books
                        del st.session_state.df_authors
                        st.success(f"Fertig! Liste bereinigt.")
                        time.sleep(2)
                        st.rerun()

        # --- TAB 3: LISTE ---
        elif selected_nav == "🔍 Liste":
            c_head, c_btn = st.columns([2,1])
            with c_head: st.header("Sammlung")
            with c_btn: 
                if st.button("🔄 Tabelle neu laden"): force_reload()

            df_books = st.session_state.df_books.copy()
            if not df_books.empty:
                df_books["Löschen"] = False
                df_books["Cover"] = df_books["Cover"].replace(NO_COVER_MARKER, None)
                
                search = st.text_input("🔍 Suchen:", placeholder="Titel...", key="search_box_fixed")
                
                df_books["_Nachname"] = df_books["Autor"].apply(get_lastname)
                df_view = df_books.sort_values(by="_Nachname")
                
                if search:
                    clean_search = search.strip()
                    df_view = df_view[
                        df_view["Titel"].astype(str).str.contains(clean_search, case=False) |
                        df_view["Autor"].astype(str).str.contains(clean_search, case=False)
                    ]
                
                with st.form("list_view"):
                    edited_df = st.data_editor(
                        df_view,
                        column_order=["Titel", "Autor", "Bewertung", "Cover", "Löschen"],
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
                            del st.session_state.df_books
                            st.success("Gelöscht!")
                            time.sleep(1)
                            st.rerun()

                st.markdown("---")
                with st.expander("🔧 Wartung & fehlende Cover"):
                    st.write("Erzwingt Suche (Google + OpenLibrary).")
                    if st.button("🔄 Fehlende Bilder suchen (Manuell)"):
                        with st.status("Suche...", expanded=True):
                            all_vals = ws_books.get_all_values()
                            headers = [str(h).lower() for h in all_vals[0]]
                            idx_t = -1; idx_a = -1; idx_c = -1; idx_g = -1
                            for i, h in enumerate(headers):
                                if "titel" in h: idx_t = i
                                if "autor" in h: idx_a = i
                                if h in ["cover", "bild"]: idx_c = i
                                if "genre" in h: idx_g = i
                            
                            updates = 0
                            if idx_t >= 0 and idx_c >= 0:
                                for i, row in enumerate(all_vals[1:], start=2):
                                    cov = row[idx_c] if len(row) > idx_c else ""
                                    if not cov or cov == NO_COVER_MARKER:
                                        tit = row[idx_t] if len(row) > idx_t else ""
                                        aut = row[idx_a] if len(row) > idx_a else ""
                                        if tit:
                                            st.write(f"Suche für: {tit}")
                                            nc, ng = fetch_book_data_background(tit, aut)
                                            if nc:
                                                ws_books.update_cell(i, idx_c+1, nc)
                                                updates += 1
                                            else:
                                                ws_books.update_cell(i, idx_c+1, NO_COVER_MARKER)
                                            time.sleep(1.5)
                            if updates > 0:
                                del st.session_state.df_books
                                st.success(f"{updates} Bilder gefunden!")
                                st.rerun()
                            else: st.info("Nichts gefunden.")
            else: st.info("Liste leer.")

    except Exception as e:
        st.error(f"Fehler: {e}")
        if st.button("Notfall-Reset"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
