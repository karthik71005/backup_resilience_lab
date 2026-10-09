import json
import lab.detector, lab.cli, lab.exporter, lab.backup, lab.restore, lab.vault
print("imports ok")
print(json.dumps(lab.detector.tune(), indent=1))
