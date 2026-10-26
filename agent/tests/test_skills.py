import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nova_apex.skills.doc_generator import doc_generator
from nova_apex.skills.system_admin import system_admin
from nova_apex.core.memory import agent_memory

def run_tests():
    # 1. Project Scaffolding
    struct = {
        'index.html': '<h1>Autonomous App</h1>',
        'styles.css': 'body { background: #000; color: #fff; }',
        'src/app.py': 'print("Service Running")'
    }
    scaffold_res = doc_generator.create_project_scaffold('apex_genesis', struct)
    assert scaffold_res['files_count'] == 3, "Scaffold failed"
    print(f"✓ Scaffolded {scaffold_res['files_count']} files successfully!")

    # 2. Memory Credential Storage and Retrieval
    agent_memory.store_credential('github.com', 'nova_tester', 'ApexSecret#2026_99', {'role': 'automation'})
    cred = agent_memory.get_credentials_for('github.com')
    assert cred['username'] == 'nova_tester', "Vault retrieval failed"
    print(f"✓ Vault Credential stored and retrieved: {cred['username']} @ {cred['service']}")

    # 3. Telemetry
    tel = system_admin.get_system_telemetry()
    assert tel['free_disk_gb'] > 0, "Telemetry failed"
    print(f"✓ Telemetry: OS {tel['os']}, Free Disk: {tel['free_disk_gb']} GB")

if __name__ == "__main__":
    run_tests()
