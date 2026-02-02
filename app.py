import uuid
import os
import json
from datetime import datetime, timedelta
from nicegui import ui, app
from google.cloud import storage
from google.cloud.exceptions import NotFound

# --- Theme Configuration ---
PRIMARY_BLUE = '#134C8C'
ACCENT_YELLOW = '#F28E2B'
BG_GRAY = '#F3F4F6'

# --- Configuration ---
# We get the bucket name from an environment variable for safety/flexibility
BUCKET_NAME = 'paste-it'

# Initialize GCS Client (Cloud Run uses the attached Service Account automatically)
storage_client = storage.Client()

# --- Editor State ---
# Store editor objects in memory indexed by client ID
active_editors = {}

LANG_OPTIONS = {
    'sql': 'SQL',
    'python': 'Python',
    'yaml': 'Terraform / YAML',
    'javascript': 'JavaScript',
    'text': 'Plain Text'
}

# --- Helper Functions (GCS) ---
def save_to_gcs(paste_id, data):
    """Saves the paste data dict to GCS as a JSON file."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"{paste_id}.json")
    
    # Upload as JSON
    blob.upload_from_string(
        data=json.dumps(data),
        content_type='application/json'
    )

def get_from_gcs(paste_id):
    """Retrieves paste data from GCS. Returns None if not found or expired."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"{paste_id}.json")

    try:
        data_str = blob.download_as_text()
        data = json.loads(data_str)
        
        # Check Expiry
        expires_at = datetime.fromisoformat(data['expires_at'])
        if datetime.now() > expires_at:
            print(f"Paste {paste_id} expired.")
            return None
            
        return data
    except NotFound:
        return None
    except Exception as e:
        print(f"Error reading GCS: {e}")
        return None

# --- UI Layout Components ---
def apply_styles():
    ui.colors(primary=PRIMARY_BLUE, accent=ACCENT_YELLOW)
    ui.query('body').style(f'background-color: {BG_GRAY}; font-family: "Inter", sans-serif;')

def header():
    with ui.header().classes('items-center justify-between shadow-md').style(f'background-color: {PRIMARY_BLUE}'):
        with ui.row().classes('items-center cursor-pointer').on('click', lambda: ui.navigate.to('/')):
            ui.icon('code', size='md').classes('text-white')
            ui.label('INTERNAL PASTE').classes('text-xl font-bold text-white tracking-tight')
        ui.button('New Paste', icon='add', on_click=lambda: ui.navigate.to('/')).props('flat color=white')

# --- Page: Create Paste ---
@ui.page('/')
def index():
    apply_styles()
    header()
    
    client_id = ui.context.client.id

    with ui.column().classes('w-full max-w-5xl mx-auto mt-8 p-4'):
        with ui.card().classes('w-full p-0 shadow-lg border-none overflow-hidden'):
            
            # Toolbar
            with ui.row().classes('w-full p-4 bg-white border-b items-center justify-between'):
                with ui.row().classes('items-center gap-4'):
                    lang_select = ui.select(
                        options=LANG_OPTIONS, 
                        value='sql', 
                    ).props('outlined dense').classes('w-48')
                    ui.label('Expires in 30 days').classes('text-xs text-gray-400 uppercase font-bold')
                
                ui.button('Generate Link', icon='share', on_click=lambda: handle_submit()) \
                    .props(f'color=accent text-color=white').classes('px-6 shadow-md')

            # Dynamic Editor Container
            editor_container = ui.column().classes('w-full')
            
            def refresh_editor():
                current_text = active_editors[client_id].value if client_id in active_editors else ""
                
                editor_container.clear()
                with editor_container:
                    active_editors[client_id] = ui.codemirror(
                        value=current_text, 
                        language=lang_select.value
                    ).classes('w-full h-[50vh] text-base')
            
            lang_select.on_value_change(refresh_editor)
            refresh_editor()

    async def handle_submit():
        editor = active_editors.get(client_id)
        if not editor or not editor.value.strip():
            ui.notify('Snippet is empty!', type='warning')
            return
        
        # Generate ID and Expiry
        pid = str(uuid.uuid4())[:8]
        expiry = (datetime.now() + timedelta(days=30)).isoformat()
        
        # Prepare Data Payload
        payload = {
            "id": pid,
            "code": editor.value,
            "lang": lang_select.value,
            "expires_at": expiry
        }
        
        try:
            # Save to Cloud Storage
            save_to_gcs(pid, payload)
            ui.navigate.to(f'/v/{pid}')
        except Exception as e:
            ui.notify(f'Upload failed: {str(e)}', type='negative')

# --- Page: View Paste ---
@ui.page('/v/{paste_id}')
def view_paste(paste_id: str):
    apply_styles()
    header()

    # Retrieve from GCS
    data = get_from_gcs(paste_id)
    
    with ui.column().classes('w-full max-w-6xl mx-auto mt-8 p-4'):
        if data:
            code = data.get('code', '')
            lang = data.get('lang', 'text')
            expiry = data.get('expires_at', '')[:10]

            with ui.card().classes('w-full p-0 shadow-xl border-none overflow-hidden'):
                with ui.row().classes('w-full bg-gray-100 p-3 items-center justify-between border-b'):
                    ui.label(f'{LANG_OPTIONS.get(lang, lang)}').classes('text-sm font-bold text-gray-600')
                    ui.label(f'Valid until: {expiry}').classes('text-xs text-gray-500')
                
                ui.code(code, language=lang).classes('w-full text-base p-4')
            
            # --- FIX: Pre-escape the code string here ---
            # We escape backticks for JS and double quotes just in case
            escaped_code = code.replace('`', '\\`').replace('$', '\\$')
            
            ui.button('Copy Code', icon='content_copy', 
                      on_click=lambda: (ui.run_javascript(f'navigator.clipboard.writeText(`{escaped_code}`)'), 
                                      ui.notify('Copied to clipboard!'))) \
                .props('unelevated color=primary').classes('mt-4')
        else:
            with ui.card().classes('w-full p-12 items-center text-center'):
                ui.icon('sentiment_dissatisfied', size='xl', color='grey-400')
                ui.label('Snippet Expired or Not Found').classes('text-xl text-gray-500 mt-4')
                ui.button('Go Home', on_click=lambda: ui.navigate.to('/')).classes('mt-4')

# --- Cloud Run Execution ---
# IMPORTANT: This block is critical for Cloud Run to avoid crash loops
if __name__ in {"__main__", "__mp_main__"}:
    port = int(os.environ.get('PORT', 8080))
    ui.run(
        title='Paste Service', 
        host='0.0.0.0', 
        port=port, 
        storage_secret='team_internal_secret_key',
        show=False,   # Disable browser auto-open
        reload=False  # Disable hot-reload
    )