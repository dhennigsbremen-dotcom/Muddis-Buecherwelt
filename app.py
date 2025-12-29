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
    
    /* Buch-Karte Design */
    .book-title { font-size: 1.4rem; font-weight: 700; margin-bottom: 0px; color: #2c3e50 !important; }
    .book-meta { font-size: 1.0rem; color: #7f8c8d !important; font-style: italic; margin-bottom: 5px; }
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

def search_and_process_book(query):
    """Sucht Infos, BEHÄLT aber den deutschen Titel bei"""
    # Wir nehmen standardmäßig DEINE Eingabe als Titel (als Title Case formatiert)
    # Damit bleibt "Harry Potter und der Stein der Weisen" erhalten, auch wenn die API "Philosopher's Stone" liefert.
    book_data = {"Titel": query, "Autor": "Unbekannt", "Genre": "Roman", "Cover": ""}
    
    if not query: 
        return None
    
    try:
        clean_query = query.replace(" ", "+")
        url = f"https://openlibrary.org/search.json?q={clean_query}&limit=1"
        headers = {"User-Agent": "MamasBuecherweltApp/1.0"}
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("numFound", 0) > 0 and len(data.get("docs", [])) > 0:
                item = data["docs"][0]
                
                # WICHTIG: Wir überschreiben den Titel NICHT mehr mit dem API-Ergebnis.
                # Wir holen nur Autor und Cover.
                
                # Autor
                authors = item.get("author_name", [])
                if authors:
                    book_data["Autor"] = authors[0]
                
                # Cover
                cover_id = item.get("cover_i")
                if cover_id:
                    book_data["Cover"] = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                
                # Genre
                subjects = item.get("subject", [])
                if subjects:
                    raw_genre = subjects[0]
                    try:
                        translator = GoogleTranslator(source='auto', target='de')
                        book_data["Genre"] = translator.translate(raw_genre)
                    except:
                        book_data["Genre"] = raw_genre
            else:
                st.warning(f"Keine automatischen Infos gefunden. Speichere deine Eingabe.")
        else:
            st.error(f"API Fehler: {response.status_code}")
                    
    except Exception as e: 
        st.error(f"Fehler bei der Suche: {e}")
        
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
                title_input = st.text_input("Titel (auf Deutsch):", placeholder="z.B. Harry Potter und der Stein der Weisen")
                rating = st.slider("Bewertung:", 1, 5, 5)
                submitted = st.form_submit_button("💾 SPEICHERN & SUCHEN")
                
                if submitted and title_input:
                    with st.spinner("Hole Autor & Cover..."):
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

        # --- TAB 2: MEINE LISTE ---
        with tab2:
            st.header("Deine Sammlung")
            
            if not df.empty:
                # --- MULTI-LÖSCHEN ---
                with st.expander("🗑 Bücher löschen (Menü öffnen)"):
                    st.write("Wähle hier alle Bücher aus, die weg sollen:")
                    all_titles = df["Titel"].tolist()
                    
                    # Multiselect erlaubt mehrere Auswahlen gleichzeitig
                    delete_list = st.multiselect("Bücher auswählen:", all_titles)
                    
                    if delete_list:
                        if st.button(f"{len(delete_list)} Buch/Bücher endgültig löschen"):
                            try:
                                with st.spinner("Lösche Daten..."):
                                    # Wir müssen die Zeilennummern finden
                                    rows_to_delete = []
                                    for title in delete_list:
                                        # Wir suchen nach dem Titel (Achtung: Findet nur das erste Vorkommen)
                                        cell = worksheet.find(title)
                                        rows_to_delete.append(cell.row)
                                    
                                    # WICHTIG: Wir sortieren die Zeilennummern ABSTEIGEND (von unten nach oben).
                                    # Warum? Wenn wir Zeile 5 löschen, wird Zeile 6 zur neuen Zeile 5.
                                    # Wenn wir von unten löschen, bleiben die oberen Nummern korrekt.
                                    rows_to_delete = sorted(list(set(rows_to_delete)), reverse=True)
                                    
                                    for row_num in rows_to_delete:
                                        worksheet.delete_rows(row_num)
                                        time.sleep(0.5) # Kurze Pause zur Sicherheit für Google API
                                    
                                    st.success("Erfolgreich gelöscht!")
                                    time.sleep(1)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Fehler beim Löschen: {e}")

                st.markdown("---")
                
                # SUCHE & SORTIERUNG
                col_search, col_sort = st.columns([2, 1])
                with col_search:
                    search_term = st.text_input("🔍 Suche:", placeholder="Titel oder Autor...")
                with col_sort:
                    sort_option = st.selectbox("Sortieren:", ["Neueste zuerst", "Titel (A-Z)", "Autor (A-Z)", "Beste Bewertung"])
                
                df_display = df.copy()
                if search_term:
                    df_display = df_display[
                        df_display["Titel"].astype(str).str.contains(search_term, case=False) | 
                        df_display["Autor"].astype(str).str.contains(search_term, case=False)
                    ]
                
                if sort_option == "Titel (A-Z)": df_display = df_display.sort_values(by="Titel")
                elif sort_option == "Autor (A-Z)": df_display = df_display.sort_values(by="Autor")
                elif sort_option == "Beste Bewertung": df_display = df_display.sort_values(by="Bewertung", ascending=False)
                else: df_display = df_display.iloc[::-1]

                st.write(f"Zeige {len(df_display)} Bücher:")
                
                for index, row in df_display.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        with c1:
                            if row.get("Cover"): st.image(row["Cover"], width=80)
                            else: st.write("📚")
                        with c2:
                            st.markdown(f'<div class="book-title">{row["Titel"]}</div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="book-meta">Von {row["Autor"]} | {row["Genre"]}</div>', unsafe_allow_html=True)
                            try: stars = "⭐" * int(float(row["Bewertung"]))
                            except: stars = ""
                            st.write(stars)
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
