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
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
 # --- FUNKTIONEN ---
@st.cache_resource
def get_connection():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # TRICK: Wir schauen, ob wir in der Cloud sind oder lokal
    if "gcp_service_account" in st.secrets:
        # Wir sind in der Cloud und laden die Infos aus den sicheren Secrets
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        # Wir sind lokal auf deinem PC und nutzen die Datei
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        
    client = gspread.authorize(creds)
    return client
            data = response.json()
            if "items" in data:
                info = data["items"][0]["volumeInfo"]
                book_data["Titel"] = info.get("title", query)
                book_data["Autor"] = ", ".join(info.get("authors", ["Unbekannt"]))
                book_data["Cover"] = info.get("imageLinks", {}).get("thumbnail", "")
                raw = info.get("categories", ["Roman"])
                try: book_data["Genre"] = GoogleTranslator(source='auto', target='de').translate(raw[0])
                except: book_data["Genre"] = raw[0]
    except Exception as e: print(f"Fehler: {e}")
    return book_data

# --- HAUPTPROGRAMM ---
def main():
    st.title("📚 Mamas Bücherwelt")
    
    try:
        client = get_connection()
        sheet_name = "Mamas Bücherliste"
        sh = client.open(sheet_name)
        worksheet = sh.sheet1
        
        # --- DATEN LADEN & BEREINIGEN ---
        data = worksheet.get_all_records()
        df = pd.DataFrame()
        
        if data:
            df = pd.DataFrame(data)
            
            # Spalten sicher umbenennen
            rename_map = {}
            if "Cover_Link" in df.columns: rename_map["Cover_Link"] = "Cover"
            if "Bild" in df.columns: rename_map["Bild"] = "Cover"
            if "Sterne" in df.columns: rename_map["Sterne"] = "Bewertung"
            if "Stars" in df.columns: rename_map["Stars"] = "Bewertung"
            
            if rename_map:
                df = df.rename(columns=rename_map)
                
            # Sicherstellen, dass Spalten existieren
            if "Cover" not in df.columns: df["Cover"] = ""
            if "Bewertung" not in df.columns: df["Bewertung"] = 0
            if "Titel" not in df.columns: df["Titel"] = ""
            if "Autor" not in df.columns: df["Autor"] = ""

        # TABS ERSTELLEN
        tab1, tab2, tab3 = st.tabs(["📖 Neues Buch", "🔍 Meine Liste", "📊 Statistik"])
        
        # --- TAB 1: EINGABE ---
        with tab1:
            st.header("Neues Buch eintragen")
            with st.form("quick_add_form", clear_on_submit=True):
                title_input = st.text_input("Titel:", placeholder="z.B. Harry Potter")
                rating = st.slider("Bewertung:", 1, 5, 5)
                submitted = st.form_submit_button("💾 SPEICHERN & SUCHEN")
                
                if submitted and title_input:
                    with st.spinner("Suche Infos..."):
                        book_info = search_and_process_book(title_input)
                        worksheet.append_row([
                            book_info["Titel"],
                            book_info["Autor"],
                            book_info["Genre"],
                            rating,
                            book_info["Cover"]
                        ])
                        st.success(f"Gespeichert: {book_info['Titel']}")
                        time.sleep(1)
                        st.rerun()

        # --- TAB 2: MEINE LISTE (MIT SUCHE & SORTIERUNG) ---
        with tab2:
            st.header("Deine Sammlung")
            
            if not df.empty:
                # 1. LÖSCHEN (Expander)
                with st.expander("🗑 Buch löschen"):
                    # Wir zeigen hier IMMER alle Titel an, unabhängig von der Suche unten
                    all_titles = df["Titel"].tolist()
                    del_choice = st.selectbox("Buch wählen:", ["(Auswählen)"] + all_titles)
                    if st.button("Löschen"):
                        if del_choice != "(Auswählen)":
                            try:
                                cell = worksheet.find(del_choice)
                                worksheet.delete_rows(cell.row)
                                st.success("Gelöscht!")
                                time.sleep(1)
                                st.rerun()
                            except: st.error("Nicht gefunden.")

                st.markdown("---")
                
                # 2. SUCHE & SORTIERUNG
                # Wir machen zwei Spalten: Links Suche, Rechts Sortierung
                col_search, col_sort = st.columns([2, 1])
                
                with col_search:
                    search_term = st.text_input("🔍 Suche nach Titel oder Autor...", placeholder="Tippe hier...")
                
                with col_sort:
                    sort_option = st.selectbox("Sortieren nach:", 
                                               ["Neueste zuerst", "Titel (A-Z)", "Autor (A-Z)", "Beste Bewertung"])
                
                # --- LOGIK ANWENDEN ---
                # Wir erstellen eine Kopie zum Filtern, damit das Original df erhalten bleibt
                df_display = df.copy()
                
                # A) Filter (Suche)
                if search_term:
                    # Sucht im Titel ODER im Autor (alles in Kleinbuchstaben umgewandelt für Treffergenauigkeit)
                    df_display = df_display[
                        df_display["Titel"].astype(str).str.contains(search_term, case=False) | 
                        df_display["Autor"].astype(str).str.contains(search_term, case=False)
                    ]
                
                # B) Sortierung
                if sort_option == "Titel (A-Z)":
                    df_display = df_display.sort_values(by="Titel")
                elif sort_option == "Autor (A-Z)":
                    df_display = df_display.sort_values(by="Autor")
                elif sort_option == "Beste Bewertung":
                    df_display = df_display.sort_values(by="Bewertung", ascending=False)
                else: # "Neueste zuerst" (Standard)
                    # Wir drehen die Liste einfach um (letzte Einträge zuerst)
                    df_display = df_display.iloc[::-1]

                # 3. ANZEIGE DER KARTEN
                st.write(f"Zeige {len(df_display)} Buch/Bücher:")
                
                for index, row in df_display.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        with c1:
                            if row.get("Cover"): 
                                st.image(row["Cover"], width=80)
                            else:
                                st.write("📚")
                        with c2:
                            st.markdown(f'<div class="book-title">{row["Titel"]}</div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="book-meta">Von {row["Autor"]} | {row["Genre"]}</div>', unsafe_allow_html=True)
                            try:
                                stars = "⭐" * int(row["Bewertung"])
                            except:
                                stars = ""
                            st.write(stars)
            else:
                st.info("Noch keine Bücher vorhanden.")

        # --- TAB 3: STATISTIK ---
        with tab3:
            st.header("Überblick")
            if not df.empty:
                c1, c2, c3 = st.columns(3)
                c1.metric("Anzahl", len(df))
                if "Autor" in df.columns: c2.metric("Top Autor", df["Autor"].mode()[0] if not df["Autor"].empty else "-")
                if "Genre" in df.columns: c3.metric("Top Genre", df["Genre"].mode()[0] if not df["Genre"].empty else "-")
                
                st.markdown("---")
                total = len(df)
                sc1, sc2 = st.columns(2)
                
                with sc1:
                    st.subheader("Nach Genre")
                    if "Genre" in df.columns:
                        for g, c in df["Genre"].value_counts().items():
                            if g:
                                st.write(f"**{g}**: {c}")
                                st.progress(int((c/total)*100)/100)
                with sc2:
                    st.subheader("Top Autoren")
                    if "Autor" in df.columns:
                        for a, c in df["Autor"].value_counts().head(5).items():
                            if a:
                                st.write(f"**{a}**: {c}")
                                st.progress(int((c/total)*100)/100)
            else:
                st.write("Keine Daten.")

    except Exception as e:
        st.error(f"Ein Fehler ist aufgetreten: {e}")

if __name__ == "__main__":
    main()