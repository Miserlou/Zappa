#!/usr/bin/env python3

import json
from pathlib import Path


readme_file = Path('README.md')
readme = readme_file.read_text().splitlines()

start = readme.index('<!-- list-of-configs -->')
end = readme.index('<!-- /list-of-configs -->')

del readme[start+1:end]

readme.insert(start+1, '')
readme.insert(start+2, '| ID | Default | Summary |')
readme.insert(start+3, '| --- | --- | --- |')

for config_file in sorted(Path('configs').glob('*.json')):
    end = readme.index('<!-- /list-of-configs -->')
    config = json.loads(config_file.read_text())
    readme.insert(
        end, '| {id} | {default} | {summary} |'.format(**config))

readme.insert(end+1, '')

readme_file.write_text(''.join('{}\n'.format(l) for l in readme))
