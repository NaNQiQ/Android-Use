"""Stage an Android-only plugin with upstream license and complete editable UI."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def stage():
    meta = json.loads((ROOT / 'plugin.json').read_text(encoding='utf-8'))
    target = (ROOT / 'dist/android-use').resolve()
    if target.parent != (ROOT / 'dist').resolve() or target.name != 'android-use':
        raise ValueError('Invalid package target')
    if target.exists(): shutil.rmtree(target)
    target.mkdir(parents=True)
    def copy(source, dest):
        path = target / dest
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, path)
    copy('plugin.json', 'plugin.json')
    copy('README.md', 'README.md')
    overlay = {k: meta[k] for k in ('name','version','description','author','license')}
    overlay.update(skills='./skills/', mcpServers='./.mcp.json', interface=meta['extensions']['com.openai']['interface'],
                   extensions={'com.openai': {'onboardingSkill': './skills/android-use-setup/SKILL.md'}})
    (target / '.codex-plugin').mkdir()
    (target / '.codex-plugin/plugin.json').write_text(json.dumps(overlay, ensure_ascii=False, indent=2), encoding='utf-8')
    mcp = {'mcpServers': {'android_use': {'type': 'stdio', 'command': 'python',
           'args': ['${PLUGIN_ROOT}/scripts/launch_android.py'], 'cwd': '${PLUGIN_ROOT}'}}}
    for name in ('mcp.json', '.mcp.json'):
        (target / name).write_text(json.dumps(mcp, indent=2), encoding='utf-8')
    for source in (ROOT/'skills').rglob('*'):
        if source.is_file(): copy(source.relative_to(ROOT), Path('skills')/source.relative_to(ROOT/'skills'))
    for source in (ROOT/'server').glob('android*.py'): copy(source.relative_to(ROOT), source.relative_to(ROOT))
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.android.md', 'requirements-android.txt',
                 'assets/android-screen.html', 'assets/android-icon.svg', 'assets/android-use-demo.png', 'NOTICE.android.md', 'scripts/launch_android.py',
                 'scripts/install-android.ps1', 'VALIDATION.android.md', 'README.en.md', 'tests/test_android.py', 'tests/test_android_live.py'):
        copy(name, name)
    for source in (ROOT/'ui').rglob('*'):
        rel = source.relative_to(ROOT)
        if source.is_file() and not any(p in ('node_modules', '__pycache__') for p in rel.parts): copy(rel,rel)
    marketplace = json.loads((ROOT/'.agents/plugins/marketplace.json').read_text(encoding='utf-8'))
    marketplace['name'] = 'android-use-local'
    marketplace['interface'] = {'displayName': 'Android Use Local'}
    marketplace['plugins'] = [{'name':'android-use','source':{'source':'local','path':'./dist/android-use'},
                               'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]
    marketroot = ROOT/'dist/marketplace-android'
    (marketroot/'.agents/plugins').mkdir(parents=True, exist_ok=True)
    # Source resides beneath the marketplace root; root traversal is rejected by Codex.
    marketplace['plugins'][0]['source']['path'] = './android-use'
    installed_source = marketroot/'android-use'
    if installed_source.exists():
        if installed_source.resolve().parent != marketroot.resolve(): raise ValueError('Invalid staging path')
        shutil.rmtree(installed_source)
    shutil.copytree(target, installed_source)
    (marketroot/'.agents/plugins/marketplace.json').write_text(json.dumps(marketplace, ensure_ascii=False, indent=2), encoding='utf-8')
    return target, marketroot, meta

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage-only',action='store_true');args=p.parse_args()
    target, marketplace, meta = stage()
    if not args.stage_only:
        archive=ROOT/'dist'/f"android-use-{meta['version']}.zip"
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for file in target.rglob('*'):
                if file.is_file(): z.write(file,Path('android-use')/file.relative_to(target))
        print(archive)
    print(marketplace)
