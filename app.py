# PART 1/2 — imports, configuration, utilitaires, DB, CRUD, exports (clients), génération PDF (unique)
# Coller ce bloc en premier dans app.py

import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
import base64
from pathlib import Path
import io

# Check availability of optional libs
REPORTLAB_AVAILABLE = True
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
except ModuleNotFoundError:
    REPORTLAB_AVAILABLE = False

OPENPYXL_AVAILABLE = True
try:
    import openpyxl  # noqa: F401
except ModuleNotFoundError:
    OPENPYXL_AVAILABLE = False

# Page config
st.set_page_config(page_title="Application de Facturation", page_icon="🧾", layout="wide")

DB_PATH = "facturation.db"
LOGOS_DIR = Path("logos")
LOGOS_DIR.mkdir(exist_ok=True)

TYPES_FACTURATION = ["m²", "ml", "m³", "pièce", "unité", "forfait", "jour", "heure"]

# -----------------------
# Helpers fichiers / images
# -----------------------
def save_uploaded_file(uploaded_file, prefix="file"):
    """Sauvegarde un fichier uploadé et retourne le chemin (ou None)."""
    if uploaded_file is None:
        return None
    try:
        suffix = Path(uploaded_file.name).suffix
        filename = f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}{suffix}"
        dest = LOGOS_DIR / filename
        with open(dest, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return str(dest)
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde du fichier: {e}")
        return None

def get_image_base64(image_path):
    try:
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except Exception:
        pass
    return None

def display_logo(logo_path, width=100):
    if logo_path and Path(logo_path).exists():
        try:
            st.image(logo_path, width=width)
        except Exception:
            st.warning("⚠️ Impossible d'afficher le logo")

# -----------------------
# DB init / connection
# -----------------------
def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fournisseur (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        adresse TEXT,
        email TEXT,
        telephone TEXT,
        logo_path TEXT,
        siret TEXT,
        tva_intra TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        prenom TEXT,
        email TEXT,
        telephone TEXT,
        adresse TEXT,
        code_postal TEXT,
        ville TEXT,
        pays TEXT DEFAULT 'France',
        logo_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS factures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT UNIQUE NOT NULL,
        client_id INTEGER NOT NULL,
        date_emission DATE NOT NULL,
        total_ht REAL NOT NULL,
        tva_pourcent REAL NOT NULL,
        montant_tva REAL NOT NULL,
        total_ttc REAL NOT NULL,
        statut TEXT DEFAULT 'En attente',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lignes_facture (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facture_id INTEGER NOT NULL,
        ordre INTEGER NOT NULL,
        description TEXT NOT NULL,
        type_facturation TEXT NOT NULL,
        quantite REAL NOT NULL,
        prix_unitaire REAL NOT NULL,
        total REAL NOT NULL,
        FOREIGN KEY (facture_id) REFERENCES factures(id) ON DELETE CASCADE
    )""")
    # Insert fournisseur par défaut si absent
    cursor.execute("SELECT COUNT(*) FROM fournisseur")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO fournisseur (nom, adresse, email, telephone) VALUES ('Mon Entreprise', '', '', '')")
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_PATH)

# -----------------------
# CRUD Fournisseur / Clients / Factures
# -----------------------
def get_fournisseur():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fournisseur ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "nom": row[1] or "",
            "adresse": row[2] or "",
            "email": row[3] or "",
            "telephone": row[4] or "",
            "logo_path": row[5] or "",
            "siret": row[6] if len(row) > 6 and row[6] else "",
            "tva_intra": row[7] if len(row) > 7 and row[7] else ""
        }
    except Exception as e:
        st.error(f"Erreur lors de la récupération du fournisseur: {e}")
        return None

def update_fournisseur(data):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE fournisseur 
        SET nom=?, adresse=?, email=?, telephone=?, logo_path=?, siret=?, tva_intra=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=(SELECT id FROM fournisseur ORDER BY id DESC LIMIT 1)
        """, (
            data.get('nom',''),
            data.get('adresse',''),
            data.get('email',''),
            data.get('telephone',''),
            data.get('logo_path',''),
            data.get('siret',''),
            data.get('tva_intra','')
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erreur lors de la mise à jour du fournisseur: {e}")
        return False

def get_all_clients():
    try:
        conn = get_connection()
        df = pd.read_sql_query("SELECT * FROM clients ORDER BY created_at DESC", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erreur lors de la récupération des clients: {e}")
        return pd.DataFrame()

def add_client(data):
    """
    Ajoute un client — le schéma attendu : nom, prenom, email, telephone, adresse, code_postal, ville, pays, logo_path.
    Retourne (True, client_id) ou (False, error_message).
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO clients (nom, prenom, email, telephone, adresse, code_postal, ville, pays, logo_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('nom',''),
            data.get('prenom',''),
            data.get('email',''),
            data.get('telephone',''),
            data.get('adresse',''),
            data.get('code_postal',''),
            data.get('ville',''),
            data.get('pays','France'),
            data.get('logo_path','')
        ))
        conn.commit()
        client_id = cursor.lastrowid
        conn.close()
        return True, client_id
    except Exception as e:
        return False, f"Erreur: {e}"

def get_client_by_id(client_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id=?", (client_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "nom": row[1],
            "prenom": row[2] or "",
            "email": row[3] or "",
            "telephone": row[4] or "",
            "adresse": row[5] or "",
            "code_postal": row[6] or "",
            "ville": row[7] or "",
            "pays": row[8] or "France",
            "logo_path": row[9] or ""
        }
    except Exception as e:
        st.error(f"Erreur: {e}")
        return None

def delete_client(client_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM clients WHERE id=?", (client_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erreur: {e}")
        return False

def generate_numero_facture():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM factures")
        count = cursor.fetchone()[0]
        conn.close()
        year = datetime.now().year
        return f"F{year}-{count + 1:04d}"
    except Exception as e:
        st.error(f"Erreur: {e}")
        return f"F{datetime.now().year}-0001"

def save_facture(client_id, actions, total_ht, tva_pourcent, montant_tva, total_ttc, notes=""):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        numero = generate_numero_facture()
        date_emission = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
        INSERT INTO factures (numero, client_id, date_emission, total_ht, tva_pourcent, montant_tva, total_ttc, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (numero, client_id, date_emission, total_ht, tva_pourcent, montant_tva, total_ttc, notes))
        facture_id = cursor.lastrowid
        for idx, action in enumerate(actions):
            cursor.execute("""
            INSERT INTO lignes_facture (facture_id, ordre, description, type_facturation, quantite, prix_unitaire, total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                facture_id,
                idx + 1,
                action.get('description',''),
                action.get('type',''),
                action.get('quantite', 0.0),
                action.get('prix_unitaire', 0.0),
                action.get('total', 0.0)
            ))
        conn.commit()
        conn.close()
        return numero
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde: {e}")
        return None

def get_all_factures():
    try:
        conn = get_connection()
        query = """
        SELECT f.*, c.nom, c.prenom, c.id as client_id_ref
        FROM factures f
        JOIN clients c ON f.client_id = c.id
        ORDER BY f.date_emission DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erreur: {e}")
        return pd.DataFrame()

def get_facture_details(facture_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT f.*, c.*
        FROM factures f
        JOIN clients c ON f.client_id = c.id
        WHERE f.id = ?
        """, (facture_id,))
        facture_row = cursor.fetchone()
        cursor.execute("""
        SELECT * FROM lignes_facture
        WHERE facture_id = ?
        ORDER BY ordre
        """, (facture_id,))
        lignes = cursor.fetchall()
        conn.close()
        return facture_row, lignes
    except Exception as e:
        st.error(f"Erreur: {e}")
        return None, []

def update_facture_statut(facture_id, statut):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE factures SET statut=? WHERE id=?", (statut, facture_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erreur: {e}")
        return False

# -----------------------
# Session state init + safe rerun
# -----------------------
def init_session_state():
    """Initialise les clés utilisées dans st.session_state."""
    if 'actions_facture' not in st.session_state:
        st.session_state.actions_facture = []
    if 'last_generated_facture_id' not in st.session_state:
        st.session_state.last_generated_facture_id = None
    if 'current_client_selected' not in st.session_state:
        st.session_state.current_client_selected = None
    # lightweight rerun trigger
    if '_rerun_trigger' not in st.session_state:
        st.session_state['_rerun_trigger'] = 0

def safe_rerun():
    """
    Appelle st.experimental_rerun() si disponible, sinon déclenche un toggle minimal dans session_state
    pour forcer le rerun de Streamlit.
    """
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
            return
    except Exception:
        pass
    st.session_state['_rerun_trigger'] = st.session_state.get('_rerun_trigger', 0) + 1

# -----------------------
# Export clients -> Excel (uses OPENPYXL_AVAILABLE)
# -----------------------
def export_clients_excel():
    """Exporte la table clients en mémoire au format Excel et retourne un BytesIO."""
    try:
        clients_df = get_all_clients()
        if clients_df.empty:
            return None

        export_df = clients_df[['id', 'nom', 'prenom', 'email', 'telephone',
                                'adresse', 'code_postal', 'ville', 'pays', 'created_at']].copy()
        export_df.rename(columns={'id': 'db_id'}, inplace=True)

        if not OPENPYXL_AVAILABLE:
            st.error("Erreur lors de l'export: le module 'openpyxl' est manquant. Installez-le avec : pip install openpyxl")
            return None

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Clients', index=False)

        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Erreur lors de l'export: {e}")
        return None

# -----------------------
# get_facture_by_numero
# -----------------------
def get_facture_by_numero(numero: str):
    """Retourne l'id de la facture pour un numéro donné (ou None)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM factures WHERE numero = ?", (numero,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        st.error(f"Erreur lors de la recherche de la facture: {e}")
        return None

# -----------------------
# Génération du PDF (unique)
# -----------------------
def generate_facture_pdf(facture_id):
    """Génère un PDF en mémoire (BytesIO) pour la facture donnée (ReportLab)."""
    if not REPORTLAB_AVAILABLE:
        st.error("Le module 'reportlab' n'est pas installé. Installez-le: python -m pip install reportlab")
        return None

    try:
        fournisseur = get_fournisseur()
        facture_row, lignes = get_facture_details(facture_id)
        if not facture_row:
            st.error("Facture introuvable.")
            return None

        client_id = facture_row[2] if len(facture_row) > 2 else None
        client = get_client_by_id(client_id) if client_id else None

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setTitle("Facture_" + str(facture_row[1]) if len(facture_row) > 1 else "Facture")

        # Logos (silencieux en cas d'erreur)
        try:
            if fournisseur and fournisseur.get("logo_path") and Path(fournisseur["logo_path"]).exists():
                img = ImageReader(fournisseur["logo_path"])
                c.drawImage(img, 15*mm, 260*mm, width=45*mm, height=25*mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

        try:
            if client and client.get("logo_path") and Path(client["logo_path"]).exists():
                img_c = ImageReader(client["logo_path"])
                c.drawImage(img_c, 150*mm, 260*mm, width=45*mm, height=25*mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

        # Infos fournisseur
        y = 250*mm
        c.setFont("Helvetica-Bold", 12)
        if fournisseur:
            c.drawString(15*mm, y, fournisseur.get("nom", ""))
            c.setFont("Helvetica", 9)
            y -= 5*mm
            if fournisseur.get("adresse"):
                c.drawString(15*mm, y, fournisseur.get("adresse"))
                y -= 4*mm
            if fournisseur.get("email"):
                c.drawString(15*mm, y, fournisseur.get("email"))
                y -= 4*mm
            if fournisseur.get("telephone"):
                c.drawString(15*mm, y, fournisseur.get("telephone"))
                y -= 4*mm
            y = 225*mm
        else:
            y = 225*mm

        # Infos client
        c.setFont("Helvetica-Bold", 11)
        client_y = 235*mm
        if client:
            c.drawString(15*mm, client_y, "Facturer à :")
            client_y -= 5*mm
            c.setFont("Helvetica", 10)
            c.drawString(15*mm, client_y, f"{client.get('nom','')} {client.get('prenom','')}")
            client_y -= 4*mm
            if client.get("adresse"):
                c.drawString(15*mm, client_y, client.get("adresse"))
                client_y -= 4*mm
            addr_line = f"{client.get('code_postal','')} {client.get('ville','')}".strip()
            if addr_line:
                c.drawString(15*mm, client_y, addr_line)
                client_y -= 4*mm

        # Infos facture (numéro, date, statut)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(120*mm, 235*mm, "FACTURE")
        c.setFont("Helvetica", 10)
        c.drawString(120*mm, 230*mm, "N° " + str(facture_row[1]) if len(facture_row) > 1 else "N°")
        c.drawString(120*mm, 224*mm, "Date: " + str(facture_row[3]) if len(facture_row) > 3 else "Date:")
        statut_val = facture_row[8] if len(facture_row) > 8 else ""
        c.drawString(120*mm, 218*mm, "Statut: " + str(statut_val))

        # Entête & lignes
        table_top = 200*mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(15*mm, table_top, "Description")
        c.drawString(90*mm, table_top, "Type")
        c.drawRightString(120*mm, table_top, "Qté")
        c.drawRightString(140*mm, table_top, "PU (€)")
        c.drawRightString(175*mm, table_top, "Total (€)")

        c.setFont("Helvetica", 10)
        row_y = table_top - 6*mm
        for ligne in lignes:
            desc = str(ligne[3])
            typef = str(ligne[4])
            qte = ligne[5] if ligne[5] is not None else 0.0
            pu = ligne[6] if ligne[6] is not None else 0.0
            total_l = ligne[7] if ligne[7] is not None else 0.0

            c.drawString(15*mm, row_y, desc[:55])
            c.drawString(90*mm, row_y, typef)
            c.drawRightString(120*mm, row_y, f"{qte:.2f}")
            c.drawRightString(140*mm, row_y, f"{pu:.2f}")
            c.drawRightString(175*mm, row_y, f"{total_l:.2f}")
            row_y -= 6*mm

        # Totaux
        tail_y = row_y - 6*mm
        c.setFont("Helvetica-Bold", 10)
        try:
            total_ht = facture_row[4]
            tva_pourcent = facture_row[5]
            montant_tva = facture_row[6]
            total_ttc = facture_row[7]
            c.drawRightString(175*mm, tail_y, f"Total HT: {total_ht:.2f} €")
            c.drawRightString(175*mm, tail_y - 6*mm, f"TVA ({tva_pourcent:.2f}%): {montant_tva:.2f} €")
            c.drawRightString(175*mm, tail_y - 12*mm, f"Total TTC: {total_ttc:.2f} €")
        except Exception:
            pass

        # Notes
        try:
            notes_val = facture_row[9] if len(facture_row) > 9 else ""
            if notes_val:
                notes_y = tail_y - 22*mm
                c.setFont("Helvetica", 9)
                c.drawString(15*mm, notes_y, "Notes: " + str(notes_val))
        except Exception:
            pass

        # Footer
        c.setFont("Helvetica", 8)
        c.drawString(15*mm, 10*mm, "Facture générée le " + datetime.now().strftime("%d/%m/%Y %H:%M"))

        c.showPage()
        c.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"Erreur lors de la génération du PDF: {e}")
        return None
    # PART 2/2 — pages Streamlit (Configuration, Clients, Facturation, Liste), export factures, main()
# Coller ce bloc APRÈS le bloc PART 1/2 dans app.py
# IMPORTANT: PART 1/2 doit être au-dessus et contient tous les imports/utilitaires.

# -----------------------
# Export factures -> Excel
# -----------------------
def export_factures_excel():
    """Export de toutes les factures en Excel (retourne BytesIO)"""
    try:
        factures_df = get_all_factures()
        if factures_df.empty:
            return None

        client_col = 'client_id_ref' if 'client_id_ref' in factures_df.columns else ('client_ref' if 'client_ref' in factures_df.columns else None)
        cols = ['numero', client_col, 'nom', 'prenom', 'date_emission', 'total_ht', 'tva_pourcent', 'montant_tva', 'total_ttc', 'statut', 'notes']
        export_df = factures_df[[c for c in cols if c is not None and c in factures_df.columns]].copy()

        if client_col and client_col in export_df.columns:
            export_df.rename(columns={client_col: 'client_db_id'}, inplace=True)

        if not OPENPYXL_AVAILABLE:
            st.error("Erreur lors de l'export: le module 'openpyxl' est manquant. Installez-le : pip install openpyxl")
            return None

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Factures', index=False)

        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Erreur lors de l'export des factures: {e}")
        return None

# -----------------------
# Page: Configuration Fournisseur
# -----------------------
def page_fournisseur():
    st.title("⚙️ Configuration Fournisseur")

    fournisseur = get_fournisseur()
    # Logo en haut
    if fournisseur and fournisseur.get('logo_path'):
        st.markdown("**Logo (en haut)**")
        display_logo(fournisseur['logo_path'], width=220)
        st.markdown("---")

    with st.form("form_fournisseur"):
        col1, col2 = st.columns(2)
        with col1:
            nom = st.text_input("Nom de l'entreprise *", value=fournisseur['nom'] if fournisseur else "")
            email = st.text_input("Email", value=fournisseur['email'] if fournisseur else "")
            telephone = st.text_input("Téléphone", value=fournisseur['telephone'] if fournisseur else "")
            siret = st.text_input("SIRET", value=fournisseur.get('siret', '') if fournisseur else "")
        with col2:
            adresse = st.text_area("Adresse complète", value=fournisseur['adresse'] if fournisseur else "")
            tva_intra = st.text_input("N° TVA Intracommunautaire", value=fournisseur.get('tva_intra', '') if fournisseur else "")
            logo_file = st.file_uploader("📷 Choisir un logo (PNG/JPG/JPEG)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=False)

        if st.form_submit_button("💾 Sauvegarder", type="primary"):
            if not nom:
                st.error("Le nom de l'entreprise est obligatoire.")
            else:
                logo_path = fournisseur.get('logo_path', "") if fournisseur else ""
                if logo_file is not None:
                    new_logo = save_uploaded_file(logo_file, prefix="fournisseur")
                    if new_logo:
                        logo_path = new_logo

                if update_fournisseur({
                    "nom": nom,
                    "adresse": adresse,
                    "email": email,
                    "telephone": telephone,
                    "logo_path": logo_path,
                    "siret": siret,
                    "tva_intra": tva_intra
                }):
                    st.success("✅ Informations fournisseur sauvegardées!")
                    safe_rerun()

    st.markdown("---")
    fournisseur = get_fournisseur()
    if fournisseur and fournisseur.get('logo_path'):
        st.subheader("Logo actuel")
        display_logo(fournisseur['logo_path'], width=150)
    else:
        st.info("Aucun logo fournisseur enregistré.")

# -----------------------
# Page: Gestion des Clients
# -----------------------
def page_clients():
    st.title("👥 Gestion des Clients")

    tab1, tab2, tab3 = st.tabs(["📝 Ajouter", "📋 Liste", "📤 Export"])

    with tab1:
        st.info("L'ID client est généré automatiquement lors de l'ajout.")
        with st.form("form_client"):
            col1, col2 = st.columns(2)
            with col1:
                nom = st.text_input("Nom *")
                prenom = st.text_input("Prénom")
                email = st.text_input("Email")
                telephone = st.text_input("Téléphone")
            with col2:
                adresse = st.text_area("Adresse")
                code_postal = st.text_input("Code postal")
                ville = st.text_input("Ville")
                pays = st.text_input("Pays", value="France")
                logo_file = st.file_uploader("📷 Logo du client (optionnel)", type=['png', 'jpg', 'jpeg'])

            if st.form_submit_button("➕ Ajouter", type="primary"):
                if not nom:
                    st.error("Le nom est obligatoire.")
                else:
                    logo_path = ""
                    if logo_file is not None:
                        logo_path = save_uploaded_file(logo_file, prefix=f"client_{nom}") or ""

                    success, result = add_client({
                        "nom": nom,
                        "prenom": prenom,
                        "email": email,
                        "telephone": telephone,
                        "adresse": adresse,
                        "code_postal": code_postal,
                        "ville": ville,
                        "pays": pays,
                        "logo_path": logo_path
                    })
                    if success:
                        st.success(f"✅ Client ajouté (ID interne = {result})")
                        safe_rerun()
                    else:
                        st.error(f"❌ {result}")

    with tab2:
        clients_df = get_all_clients()
        if not clients_df.empty:
            st.metric("Total Clients", len(clients_df))
            display_df = clients_df[['id', 'nom', 'prenom', 'email', 'telephone', 'ville', 'pays']].copy()
            display_df.rename(columns={'id': 'db_id'}, inplace=True)
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.divider()
            col1, col2 = st.columns([3, 1])
            with col1:
                options = [""] + [(int(row['id']), f"{row['id']} - {row['nom']} {row['prenom']}") for _, row in clients_df.iterrows()]
                client_sel = st.selectbox("Sélectionner un client", options, format_func=lambda x: x[1] if x else "Sélectionner")
            with col2:
                if client_sel and st.button("🗑️ Supprimer"):
                    if delete_client(client_sel[0]):
                        st.success("✅ Client supprimé")
                        safe_rerun()
        else:
            st.info("ℹ️ Aucun client enregistré pour le moment.")

    with tab3:
        st.subheader("📤 Exporter la base clients")
        st.write("Téléchargement Excel (.xlsx) — nécessite openpyxl.")
        if st.button("📥 Générer le fichier clients (Excel)", type="primary"):
            excel_file = export_clients_excel()
            if excel_file:
                st.download_button(
                    label="💾 Télécharger la base clients (Excel)",
                    data=excel_file,
                    file_name=f"clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success("✅ Fichier prêt à télécharger!")
            else:
                st.warning("⚠️ Aucune donnée à exporter ou 'openpyxl' manquant.")

# -----------------------
# Page: Créer une Facture
# -----------------------
def page_facturation():
    st.title("🧾 Nouvelle Facture")

    clients_df = get_all_clients()
    if clients_df.empty:
        st.warning("⚠️ Ajoutez d'abord des clients")
        return

    st.subheader("1️⃣ Sélection du client")
    options = [(int(r['id']), f"{r['id']} - {r['nom']} {r['prenom']}") for _, r in clients_df.iterrows()]
    selected = st.selectbox("Client", options, format_func=lambda x: x[1])
    client = get_client_by_id(selected[0])
    fournisseur = get_fournisseur()

    # Afficher logos
    col_logo1, col_logo2 = st.columns([1, 1])
    with col_logo1:
        st.markdown("**Logo Fournisseur**")
        if fournisseur and fournisseur.get('logo_path'):
            display_logo(fournisseur['logo_path'], width=180)
        else:
            st.info("Aucun logo fournisseur")
    with col_logo2:
        st.markdown("**Logo Client**")
        if client and client.get('logo_path'):
            display_logo(client['logo_path'], width=180)
        else:
            st.info("Aucun logo client")

    st.divider()
    st.subheader("2️⃣ Ajouter des lignes")

    with st.form("form_action", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        description = col1.text_input("Description *", "")
        type_fact = col2.selectbox("Type", TYPES_FACTURATION)
        quantite = col3.number_input("Quantité *", min_value=0.0, step=0.01, value=0.0, format="%.2f")
        prix_unitaire = col4.number_input("Prix unitaire (€) *", min_value=0.0, step=0.01, value=0.0, format="%.2f")

        if st.form_submit_button("➕ Ajouter la ligne"):
            if description and quantite > 0:
                st.session_state.actions_facture.append({
                    "description": description,
                    "type": type_fact,
                    "quantite": quantite,
                    "prix_unitaire": prix_unitaire,
                    "total": quantite * prix_unitaire
                })
                safe_rerun()
            else:
                st.error("Description et quantité (>0) obligatoires")

    # Afficher les lignes ajoutées
    if st.session_state.actions_facture:
        st.subheader("3️⃣ Récapitulatif")
        df_actions = pd.DataFrame([{
            "#": i+1,
            "Description": a['description'],
            "Type": a['type'],
            "Quantité": f"{a['quantite']:.2f}",
            "PU (€)": f"{a['prix_unitaire']:.2f}",
            "Total (€)": f"{a['total']:.2f}"
        } for i, a in enumerate(st.session_state.actions_facture)])
        st.dataframe(df_actions, use_container_width=True, hide_index=True)

        total_ht = sum(a['total'] for a in st.session_state.actions_facture)
        col_notes, col_tva = st.columns([3,1])
        notes = col_notes.text_area("Notes / Conditions de paiement")
        tva = col_tva.number_input("TVA (%)", min_value=0.0, max_value=100.0, value=20.0, step=0.1)

        montant_tva = total_ht * (tva / 100)
        total_ttc = total_ht + montant_tva

        col1, col2, col3 = st.columns(3)
        col1.metric("Total HT", f"{total_ht:.2f} €")
        col2.metric(f"TVA ({tva}%)", f"{montant_tva:.2f} €")
        col3.metric("Total TTC", f"{total_ttc:.2f} €")

        st.divider()
        c1, c2, c3 = st.columns([2,2,1])
        if c1.button("🗑️ Effacer les lignes"):
            st.session_state.actions_facture = []
            safe_rerun()

        # Enregistrer la facture dans la base et proposer le téléchargement PDF
        if c2.button("💾 Enregistrer la facture"):
            numero = save_facture(selected[0], st.session_state.actions_facture, total_ht, tva, montant_tva, total_ttc, notes)
            if numero:
                facture_id = get_facture_by_numero(numero)
                st.success("✅ Facture " + str(numero) + " enregistrée (id=" + str(facture_id) + ")")
                st.session_state.actions_facture = []
                safe_rerun()

        # Générer PDF pour la dernière facture créée (ou la facture sélectionnée)
        if c3.button("📄 Générer PDF de la dernière facture"):
            try:
                conn = get_connection()
                df = pd.read_sql_query("SELECT id FROM factures WHERE client_id = ? ORDER BY created_at DESC LIMIT 1", conn, params=(selected[0],))
                conn.close()
                if df.empty:
                    st.warning("Aucune facture trouvée pour ce client. Enregistrez d'abord la facture.")
                else:
                    fid = int(df.iloc[0]['id'])
                    pdf_buffer = generate_facture_pdf(fid)
                    if pdf_buffer:
                        st.download_button(
                            label="💾 Télécharger la facture (PDF)",
                            data=pdf_buffer,
                            file_name="facture_" + str(fid) + ".pdf",
                            mime="application/pdf"
                        )
            except Exception as e:
                st.error(f"Erreur lors de la génération du PDF: {e}")
    else:
        st.info("ℹ️ Ajoutez des lignes pour créer la facture.")

# -----------------------
# Page: Liste des Factures
# -----------------------
def page_liste_factures():
    st.title("📊 Liste des Factures")

    tab1, tab2 = st.tabs(["📋 Liste", "📤 Export"])

    with tab1:
        factures_df = get_all_factures()
        if factures_df.empty:
            st.info("ℹ️ Aucune facture enregistrée pour le moment.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Factures", len(factures_df))
            try:
                ca_ht = factures_df['total_ht'].sum()
            except Exception:
                ca_ht = 0.0
            try:
                ca_ttc = factures_df['total_ttc'].sum()
            except Exception:
                ca_ttc = 0.0
            col2.metric("Chiffre d'affaires HT", f"{ca_ht:.2f} €")
            col3.metric("Chiffre d'affaires TTC", f"{ca_ttc:.2f} €")
            en_attente_count = len(factures_df[factures_df['statut'] == 'En attente']) if 'statut' in factures_df.columns else 0
            col4.metric("En attente", en_attente_count)

            st.divider()

            statuses = factures_df['statut'].unique().tolist() if 'statut' in factures_df.columns else []
            filtre_statut = st.multiselect("Filtrer par statut", options=statuses, default=statuses)
            clients_list = factures_df['nom'].unique().tolist() if 'nom' in factures_df.columns else []
            filtre_client = st.multiselect("Filtrer par client", options=clients_list)

            df_filtered = factures_df.copy()
            if filtre_statut:
                df_filtered = df_filtered[df_filtered['statut'].isin(filtre_statut)]
            if filtre_client:
                df_filtered = df_filtered[df_filtered['nom'].isin(filtre_client)]

            for _, facture in df_filtered.iterrows():
                statut_icon = '🟢' if facture.get('statut') == 'Payée' else '🟡' if facture.get('statut') == 'En attente' else '🔴'
                header_text = f"{facture.get('numero','')} - {facture.get('nom','')} {facture.get('prenom','')} - {facture.get('date_emission','')} - {facture.get('total_ttc',0.0):.2f} € - {statut_icon} {facture.get('statut','')}"
                with st.expander(header_text):
                    facture_detail, lignes = get_facture_details(facture['id'])
                    if not facture_detail:
                        st.error("Erreur lors du chargement des détails de la facture.")
                        continue

                    colA, colB = st.columns([2, 1])
                    with colA:
                        st.write("**Informations Client :**")
                        st.write(f"- Référence interne : {facture.get('client_ref', facture.get('client_id_ref', ''))}")
                        st.write(f"- Nom : {facture.get('nom','')} {facture.get('prenom','')}")
                        if facture.get('notes'):
                            st.write("**Notes :**")
                            st.info(facture.get('notes', ''))
                    with colB:
                        st.write("**Résumé financier :**")
                        st.write(f"- Total HT: {facture.get('total_ht', 0.0):.2f} €")
                        st.write(f"- TVA ({facture.get('tva_pourcent', 0.0)}%): {facture.get('montant_tva', 0.0):.2f} €")
                        st.write(f"- **Total TTC: {facture.get('total_ttc', 0.0):.2f} €**")

                        status_options = ["En attente", "Payée", "Annulée"]
                        current_status = facture.get('statut') if facture.get('statut') in status_options else status_options[0]
                        new_status = st.selectbox("Statut", status_options, index=status_options.index(current_status), key=f"statut_{facture['id']}")
                        if new_status != current_status:
                            if st.button("Mettre à jour", key=f"maj_{facture['id']}"):
                                if update_facture_statut(facture['id'], new_status):
                                    st.success("✅ Statut mis à jour")
                                    safe_rerun()

                    st.write("**Détails des lignes :**")
                    if lignes:
                        lignes_display = []
                        for ligne_item in lignes:
                            lignes_display.append({
                                "Description": ligne_item[3],
                                "Type": ligne_item[4],
                                "Quantité": f"{ligne_item[5]:.2f}",
                                "Prix Unit. (€)": f"{ligne_item[6]:.2f}",
                                "Total (€)": f"{ligne_item[7]:.2f}"
                            })
                        st.dataframe(pd.DataFrame(lignes_display), use_container_width=True, hide_index=True)
                    else:
                        st.info("Aucune ligne de facture")

                    st.divider()
                    if st.button("📄 Télécharger cette facture (PDF)", key=f"pdf_{facture['id']}"):
                        pdf_buf = generate_facture_pdf(facture['id'])
                        if pdf_buf:
                            st.download_button(
                                label="💾 Télécharger le PDF",
                                data=pdf_buf,
                                file_name="facture_" + str(facture['numero']) + ".pdf",
                                mime="application/pdf",
                                key=f"dl_pdf_{facture['id']}"
                            )

    with tab2:
        st.subheader("📤 Export global")
        st.write("Exportez toutes les factures au format Excel (.xlsx) ou générez les PDFs individuels.")
        colE1, colE2 = st.columns(2)
        with colE1:
            if st.button("📥 Télécharger toutes les factures (Excel)", type="primary"):
                excel_buf = export_factures_excel()
                if excel_buf:
                    st.download_button(
                        label="💾 Télécharger (Excel)",
                        data=excel_buf,
                        file_name="factures_export_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        with colE2:
            st.write("Générer PDF de la dernière facture d'un client")
            clients_df_local = get_all_clients()
            if not clients_df_local.empty:
                options_local = [(int(r['id']), f"{r['id']} - {r['nom']} {r['prenom']}") for _, r in clients_df_local.iterrows()]
                sel_client = st.selectbox("Sélectionner client", options_local, format_func=lambda x: x[1])
                if st.button("📄 Générer PDF (dernière facture client)"):
                    try:
                        conn_local = get_connection()
                        df_last = pd.read_sql_query("SELECT id FROM factures WHERE client_id = ? ORDER BY created_at DESC LIMIT 1", conn_local, params=(sel_client[0],))
                        conn_local.close()
                        if df_last.empty:
                            st.warning("Aucune facture trouvée pour ce client.")
                        else:
                            fid_local = int(df_last.iloc[0]['id'])
                            pdf_buffer_local = generate_facture_pdf(fid_local)
                            if pdf_buffer_local:
                                st.download_button(
                                    label="💾 Télécharger le PDF",
                                    data=pdf_buffer_local,
                                    file_name="facture_" + str(fid_local) + ".pdf",
                                    mime="application/pdf",
                                    key=f"dl_pdf_last_{fid_local}"
                                )
                    except Exception as e:
                        st.error(f"Erreur lors de la génération du PDF: {e}")
            else:
                st.info("Aucun client enregistré pour le moment.")

# -----------------------
# Main
# -----------------------
def main():
    try:
        init_database()
        init_session_state()

        st.sidebar.title("🧾 Facturation Pro")
        st.sidebar.markdown("---")

        page = st.sidebar.radio(
            "Navigation",
            ["⚙️ Configuration", "👥 Clients", "🧾 Nouvelle Facture", "📊 Factures"],
            index=0,
            label_visibility="collapsed"
        )

        st.sidebar.markdown("---")

        fournisseur_local = get_fournisseur()
        if fournisseur_local and fournisseur_local.get('logo_path'):
            try:
                display_logo(fournisseur_local['logo_path'], width=80)
            except Exception:
                pass
        if fournisseur_local and fournisseur_local.get('nom'):
            st.sidebar.info(f"**{fournisseur_local.get('nom','')}**")

        st.sidebar.markdown("---")
        st.sidebar.caption("💡 Application de facturation — Streamlit & SQLite")

        if page == "⚙️ Configuration":
            page_fournisseur()
        elif page == "👥 Clients":
            page_clients()
        elif page == "🧾 Nouvelle Facture":
            page_facturation()
        elif page == "📊 Factures":
            page_liste_factures()

    except Exception as e:
        st.error(f"❌ Erreur: {e}")

if __name__ == "__main__":
    main()
