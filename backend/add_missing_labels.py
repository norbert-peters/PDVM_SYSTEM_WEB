"""
Fügt fehlende Labels zu Controls hinzu
"""
import asyncio
import asyncpg
import json

# Label-Mappings für Controls ohne Label
LABEL_MAPPINGS = {
    'self_name': 'Frame-Name',
    'edit_type': 'Editor-Typ',
    'tabs_def': 'Tab-Definitionen',
    'tab01_head': 'Tab 1 Überschrift',
    'tab01_gruppe': 'Tab 1 Gruppe',
    'tab02_head': 'Tab 2 Überschrift',
    'tab02_gruppe': 'Tab 2 Gruppe',
}

async def add_missing_labels():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        print("="*80)
        print("🏷️  Labels nachtragen")
        print("="*80)
        
        for name, label in LABEL_MAPPINGS.items():
            # Control laden
            row = await conn.fetchrow(
                'SELECT uid, daten FROM sys_control_dict WHERE name = $1 AND historisch = 0',
                name
            )
            
            if not row:
                print(f"  ⏭️  {name}: Nicht gefunden")
                continue
            
            daten = row['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            # Label setzen wenn fehlt
            current_label = daten.get('label')
            if not current_label or current_label == 'N/A':
                daten['label'] = label
                
                # Update
                await conn.execute(
                    'UPDATE sys_control_dict SET daten = $1, modified_at = NOW() WHERE uid = $2',
                    json.dumps(daten),
                    row['uid']
                )
                
                print(f"  ✅ {name}: Label gesetzt → '{label}'")
            else:
                print(f"  ⏭️  {name}: Hat bereits Label '{current_label}'")
        
        print("\n" + "="*80)
        print("✅ LABELS KOMPLETT")
        print("="*80)
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_missing_labels())
