import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
import base64
from pathlib import Path
import io

# Configuration de la page
st.set_page_config(
    page_title="Application de Facturation",
    page_icon="🧾",
    layout="wide"
)

# Configuration de la base de données
DB_PATH = "facturation.db"
LOGOS_DIR = Path("logos")
LOGOS_DIR.mkdir(exist_ok=True)

# Types de facturation disponibles
TYPES_FACTURATION = ["m²", "ml", "m³", "pièce", "unité", "forfait", "jour", "heure"]

# Fonctions utilitaires pour les images
def save_uploaded_file(uploaded_file, prefix=""):
    """Sauvegarde un fichier uploadé et retourne le chemin"""
    if uploaded_file is not None:
        try:
            file_extension = Path(uploaded_file.name).suffix
            filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_extension}"
            filepath = LOGOS_DIR / filename
            
            with open(filepath, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            return str(filepath)
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde du fichier: {e}")
            return None
    return None

def get_image_base64(image_path):
    """Convertit une image en base64 pour l'affichage"""
    try:
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except Exception:
        pass
    return None

def display_logo(logo_path, width=100):
    """Affiche un logo"""
    if logo_path and Path(logo_path).exists():
        try:
            st.image(logo_path, width=width)
        except Exception:
            st.warning("⚠️ Impossible d'afficher le logo")

# Fonctions de base de données
def init_database():
    """Initialise la base de données avec les tables nécessaires"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table Fournisseur
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
    )
    """)
    
    # Table Clients
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT UNIQUE NOT NULL,
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
    )
    """)
    
    # Table Factures
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS factures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero TEXT UNIQUE NOT NULL,
        client_id INTEGER NOT NULL,
        date_emission DATE NOT NULL,
        date_echeance DATE,
        total_ht REAL NOT NULL,
        tva_pourcent REAL NOT NULL,
        montant_tva REAL NOT NULL,
        total_ttc REAL NOT NULL,
        statut TEXT DEFAULT 'En attente',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    """)
    
    # Table Lignes de Facture
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
    )
    """)
    
    # Insérer un fournisseur par défaut si la table est vide
    cursor.execute("SELECT COUNT(*) FROM fournisseur")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO fournisseur (nom, adresse, email, telephone)
        VALUES ('Mon Entreprise', '', '', '')
        """)
    
    conn.commit()
    conn.close()

def get_connection():
    """Retourne une connexion à la base de données"""
    return sqlite3.connect(DB_PATH)

# Fonctions CRUD pour Fournisseur
def get_fournisseur():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fournisseur ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if row:
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
        return None
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
        """, (data['nom'], data['adresse'], data['email'], data['telephone'], 
              data['logo_path'], data.get('siret', ''), data.get('tva_intra', '')))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erreur lors de la mise à jour: {e}")
        return False

# Fonctions CRUD pour Clients
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
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO clients (client_id, nom, prenom, email, telephone, adresse, code_postal, ville, pays, logo_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data['client_id'], data['nom'], data['prenom'], data['email'], 
              data['telephone'], data['adresse'], data['code_postal'], 
              data['ville'], data['pays'], data['logo_path']))
        conn.commit()
        conn.close()
        return True, "Client ajouté avec succès"
    except sqlite3.IntegrityError:
        return False, "Cet ID client existe déjà"
    except Exception as e:
        return False, f"Erreur: {e}"

def get_client_by_id(client_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE id=?", (client_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "client_id": row[1],
                "nom": row[2],
                "prenom": row[3] or "",
                "email": row[4] or "",
                "telephone": row[5] or "",
                "adresse": row[6] or "",
                "code_postal": row[7] or "",
                "ville": row[8] or "",
                "pays": row[9] or "France",
                "logo_path": row[10] or ""
            }
        return None
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

# Fonctions CRUD pour Factures
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
            """, (facture_id, idx, action['description'], action['type'], 
                  action['quantite'], action['prix_unitaire'], action['total']))
        
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
        SELECT f.*, c.nom, c.prenom, c.client_id as client_ref
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
    # Fonctions d'export
def export_clients_excel():
    """Export de la base clients en Excel"""
    try:
        clients_df = get_all_clients()
        if clients_df.empty:
            return None
        
        export_df = clients_df[['client_id', 'nom', 'prenom', 'email', 'telephone', 
                                'adresse', 'code_postal', 'ville', 'pays', 'created_at']]
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Clients', index=False)
        
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Erreur lors de l'export: {e}")
        return None

def export_factures_excel():
    """Export de toutes les factures en Excel"""
    try:
        factures_df = get_all_factures()
        if factures_df.empty:
            return None
        
        export_df = factures_df[['numero', 'client_ref', 'nom', 'prenom', 
                                 'date_emission', 'total_ht', 'tva_pourcent', 
                                 'montant_tva', 'total_ttc', 'statut', 'notes']]
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, sheet_name='Factures', index=False)
        
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Erreur lors de l'export: {e}")
        return None

def generate_facture_html(facture_id):
    """Génère le HTML d'une facture pour export"""
    try:
        fournisseur = get_fournisseur()
        facture_row, lignes = get_facture_details(facture_id)
        
        if not facture_row:
            return None
        
        numero = facture_row[1]
        date_emission = facture_row[3]
        total_ht = facture_row[5]
        tva_pourcent = facture_row[6]
        montant_tva = facture_row[7]
        total_ttc = facture_row[8]
        statut = facture_row[9]
        notes = facture_row[10] or ""
        
        client_nom = facture_row[13]
        client_prenom = facture_row[14] or ""
        client_email = facture_row[15] or ""
        client_adresse = facture_row[17] or ""
        client_cp = facture_row[18] or ""
        client_ville = facture_row[19] or ""
        
        logo_html = ""
        if fournisseur and fournisseur['logo_path']:
            logo_base64 = get_image_base64(fournisseur['logo_path'])
            if logo_base64:
                logo_html = f'<img src="data:image/png;base64,{logo_base64}" style="max-width: 150px; max-height: 80px;">'
        
        lignes_html = ""
        for ligne in lignes:
            lignes_html += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px;">{ligne[3]}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{ligne[4]}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{ligne[5]:.2f}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{ligne[6]:.2f} €</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{ligne[7]:.2f} €</td>
            </tr>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background-color: #4CAF50; color: white; padding: 10px; }}
                td {{ padding: 8px; border: 1px solid #ddd; }}
                .totaux {{ text-align: right; margin-top: 20px; font-size: 1.1em; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    {logo_html}
                    <h2>{fournisseur['nom'] if fournisseur else ''}</h2>
                    <p>{fournisseur['adresse'] if fournisseur else ''}<br>
                    {fournisseur['email'] if fournisseur else ''}<br>
                    {fournisseur['telephone'] if fournisseur else ''}<br>
                    SIRET: {fournisseur['siret'] if fournisseur else ''}<br>
                    TVA: {fournisseur['tva_intra'] if fournisseur else ''}</p>
                </div>
                <div>
                    <h1>FACTURE</h1>
                    <p><strong>N° {numero}</strong><br>
                    Date: {date_emission}<br>
                    Statut: {statut}</p>
                </div>
            </div>
            
            <div>
                <h3>Client</h3>
                <p><strong>{client_nom} {client_prenom}</strong><br>
                {client_adresse}<br>
                {client_cp} {client_ville}<br>
                {client_email}</p>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Description</th>
                        <th>Type</th>
                        <th>Quantité</th>
                        <th>Prix Unit.</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    {lignes_html}
                </tbody>
            </table>
            
            <div class="totaux">
                <div>Total HT: {total_ht:.2f} €</div>
                <div>TVA ({tva_pourcent}%): {montant_tva:.2f} €</div>
                <div><strong>Total TTC: {total_ttc:.2f} €</strong></div>
            </div>
            
            {'<div style="margin-top: 30px;"><strong>Notes:</strong><br>' + notes + '</div>' if notes else ''}
            
            <div style="margin-top: 50px; text-align: center; color: #666;">
                <p>Facture générée le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
            </div>
        </body>
        </html>
        """
        
        return html
    except Exception as e:
        st.error(f"Erreur lors de la génération HTML: {e}")
        return None

# Initialisation de la session state
def init_session_state():
    if 'actions_facture' not in st.session_state:
        st.session_state.actions_facture = []

# Page: Configuration Fournisseur
def page_fournisseur():
    st.title("⚙️ Configuration Fournisseur")
    
    fournisseur = get_fournisseur()
    
    if fournisseur and fournisseur['logo_path']:
        st.subheader("Logo actuel")
        display_logo(fournisseur['logo_path'], width=150)
        st.divider()
    
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
            logo_file = st.file_uploader("📷 Choisir un logo", type=['png', 'jpg', 'jpeg'])
        
        if st.form_submit_button("💾 Sauvegarder", type="primary"):
            if nom:
                logo_path = fournisseur['logo_path'] if fournisseur else ""
                
                if logo_file is not None:
                    new_logo_path = save_uploaded_file(logo_file, prefix="fournisseur")
                    if new_logo_path:
                        logo_path = new_logo_path
                
                if update_fournisseur({
                    "nom": nom,
                    "adresse": adresse,
                    "email": email,
                    "telephone": telephone,
                    "logo_path": logo_path,
                    "siret": siret,
                    "tva_intra": tva_intra
                }):
                    st.success("✅ Informations sauvegardées!")
                    st.rerun()
            else:
                st.error("❌ Le nom est obligatoire!")

# Page: Gestion des Clients
def page_clients():
    st.title("👥 Gestion des Clients")
    
    tab1, tab2, tab3 = st.tabs(["📝 Ajouter", "📋 Liste", "📤 Export"])
    
    with tab1:
        with st.form("form_client"):
            col1, col2 = st.columns(2)
            
            with col1:
                client_id = st.text_input("ID Client *")
                nom = st.text_input("Nom *")
                prenom = st.text_input("Prénom")
                email = st.text_input("Email")
                telephone = st.text_input("Téléphone")
            
            with col2:
                adresse = st.text_area("Adresse")
                code_postal = st.text_input("Code postal")
                ville = st.text_input("Ville")
                pays = st.text_input("Pays", value="France")
                logo_file = st.file_uploader("📷 Logo", type=['png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("➕ Ajouter", type="primary"):
                if client_id and nom:
                    logo_path = ""
                    if logo_file:
                        logo_path = save_uploaded_file(logo_file, prefix=f"client_{client_id}") or ""
                    
                    success, message = add_client({
                        "client_id": client_id,
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
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
                else:
                    st.error("❌ ID et nom obligatoires!")
    
    with tab2:
        clients_df = get_all_clients()
        
        if not clients_df.empty:
            st.metric("Total Clients", len(clients_df))
            display_df = clients_df[['client_id', 'nom', 'prenom', 'email', 'ville']]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.divider()
            col1, col2 = st.columns([3, 1])
            with col1:
                options = [""] + [(row['id'], f"{row['client_id']} - {row['nom']}") 
                                 for _, row in clients_df.iterrows()]
                client_suppr = st.selectbox("Supprimer", options,
                    format_func=lambda x: x[1] if x else "Sélectionner")
            with col2:
                if client_suppr and st.button("🗑️ Supprimer"):
                    if delete_client(client_suppr[0]):
                        st.success("✅ Supprimé!")
                        st.rerun()
        else:
            st.info("ℹ️ Aucun client")
    
    with tab3:
        st.subheader("📤 Export Excel")
        if st.button("📥 Télécharger", type="primary"):
            excel = export_clients_excel()
            if excel:
                st.download_button(
                    "💾 Télécharger",
                    excel,
                    f"clients_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# Page: Créer Facture
def page_facturation():
    st.title("🧾 Nouvelle Facture")
    
    clients_df = get_all_clients()
    if clients_df.empty:
        st.warning("⚠️ Ajoutez d'abord des clients")
        return
    
    st.subheader("1️⃣ Client")
    options = [(r['id'], f"{r['client_id']} - {r['nom']}") for _, r in clients_df.iterrows()]
    selected = st.selectbox("Client", options, format_func=lambda x: x[1])
    
    client = get_client_by_id(selected[0])
    if not client:
        return
    
    st.divider()
    st.subheader("2️⃣ Actions")
    
    with st.form("form_action", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        desc = col1.text_input("Description *")
        type_f = col2.selectbox("Type", TYPES_FACTURATION)
        qte = col3.number_input("Quantité *", min_value=0.0, step=0.01)
        prix = col4.number_input("Prix (€) *", min_value=0.0, step=0.01)
        
        if st.form_submit_button("➕ Ajouter"):
            if desc and qte > 0:
                st.session_state.actions_facture.append({
                    "description": desc,
                    "type": type_f,
                    "quantite": qte,
                    "prix_unitaire": prix,
                    "total": qte * prix
                })
                st.rerun()
    
    if st.session_state.actions_facture:
        st.subheader("3️⃣ Récapitulatif")
        
        df_actions = pd.DataFrame([{
            "#": i+1,
            "Description": a['description'],
            "Type": a['type'],
            "Qté": f"{a['quantite']:.2f}",
            "PU": f"{a['prix_unitaire']:.2f}€",
            "Total": f"{a['total']:.2f}€"
        } for i, a in enumerate(st.session_state.actions_facture)])
        
        st.dataframe(df_actions, use_container_width=True, hide_index=True)
        
        total_ht = sum(a['total'] for a in st.session_state.actions_facture)
        
        col1, col2 = st.columns([2, 1])
        notes = col1.text_area("Notes")
        tva = col2.number_input("TVA (%)", 0.0, 100.0, 20.0, 0.1)
        
        montant_tva = total_ht * (tva / 100)
        total_ttc = total_ht + montant_tva
        
        col1, col2, col3 = st.columns(3)
        col1.metric("HT", f"{total_ht:.2f}€")
        col2.metric(f"TVA ({tva}%)", f"{montant_tva:.2f}€")
        col3.metric("TTC", f"{total_ttc:.2f}€")
        
        st.divider()
        c1, c2 = st.columns(2)
        if c1.button("🗑️ Effacer", use_container_width=True):
            st.session_state.actions_facture = []
            st.rerun()
        
        if c2.button("💾 Enregistrer", type="primary", use_container_width=True):
            num = save_facture(selected[0], st.session_state.actions_facture,
                             total_ht, tva, montant_tva, total_ttc, notes)
            if num:
                st.session_state.actions_facture = []
                st.success(f"✅ Facture {num} créée!")
                st.balloons()
                st.rerun()
                # Page: Liste Factures
def page_liste_factures():
    st.title("📊 Factures")
    
    tab1, tab2 = st.tabs(["📋 Liste", "📤 Export"])
    
    with tab1:
        factures_df = get_all_factures()
        
        if not factures_df.empty:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total", len(factures_df))
            col2.metric("CA HT", f"{factures_df['total_ht'].sum():.2f}€")
            col3.metric("CA TTC", f"{factures_df['total_ttc'].sum():.2f}€")
            col4.metric("En attente", len(factures_df[factures_df['statut']=='En attente']))
            
            st.divider()
            
            for _, f in factures_df.iterrows():
                icon = '🟢' if f['statut']=='Payée' else '🟡' if f['statut']=='En attente' else '🔴'
                
                with st.expander(f"{icon} {f['numero']} - {f['nom']} - {f['total_ttc']:.2f}€"):
                    _, lignes = get_facture_details(f['id'])
                    
                    col1, col2 = st.columns([2,1])
                    with col1:
                        st.write(f"**Client:** {f['nom']} {f['prenom']}")
                        if f['notes']:
                            st.info(f['notes'])
                    
                    with col2:
                        st.write(f"HT: {f['total_ht']:.2f}€")
                        st.write(f"TVA: {f['montant_tva']:.2f}€")
                        st.write(f"**TTC: {f['total_ttc']:.2f}€**")
                        
                        statuts = ["En attente", "Payée", "Annulée"]
                        idx = statuts.index(f['statut']) if f['statut'] in statuts else 0
                        new_stat = st.selectbox("Statut", statuts, idx, key=f"s{f['id']}")
                        if new_stat != f['statut']:
                            if st.button("MAJ", key=f"b{f['id']}"):
                                update_facture_statut(f['id'], new_stat)
                                st.rerun()
                    
                    if lignes:
                        df_l = pd.DataFrame([{
    "Description": ligne[3],
    "Type": ligne[4],
    "Qté": f"{ligne[5]:.2f}",
    "PU": f"{ligne[6]:.2f}€",
    "Total": f"{ligne[7]:.2f}€"
} for ligne in lignes])
                        st.dataframe(df_l, use_container_width=True, hide_index=True)
                    
                    if st.button("📄 Export HTML", key=f"e{f['id']}"):
                        html = generate_facture_html(f['id'])
                        if html:
                            st.download_button(
                                "💾 Télécharger",
                                html,
                                f"facture_{f['numero']}.html",
                                "text/html",
                                key=f"d{f['id']}"
                            )
        else:
            st.info("ℹ️ Aucune facture")
    
    with tab2:
        st.subheader("📤 Export Excel")
        if st.button("📥 Télécharger tout", type="primary"):
            excel = export_factures_excel()
            if excel:
                st.download_button(
                    "💾 Télécharger",
                    excel,
                    f"factures_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# Main
def main():
    try:
        init_database()
        init_session_state()
        
        st.sidebar.title("🧾 Facturation Pro")
        st.sidebar.markdown("---")
        
        page = st.sidebar.radio(
            "Navigation",
            ["⚙️ Configuration", "👥 Clients", "🧾 Nouvelle Facture", "📊 Factures"],
            label_visibility="collapsed"
        )
        
        st.sidebar.markdown("---")
        
        fournisseur = get_fournisseur()
        if fournisseur and fournisseur['nom']:
            if fournisseur['logo_path']:
                display_logo(fournisseur['logo_path'], 80)
            st.sidebar.info(f"**{fournisseur['nom']}**")
        
        st.sidebar.markdown("---")
        st.sidebar.caption("💡 Facturation Pro\nStreamlit & SQLite")
        
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