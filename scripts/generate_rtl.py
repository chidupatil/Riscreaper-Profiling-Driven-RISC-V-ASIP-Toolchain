import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

feature_map_path = Path("build/feature_map.json")
template_dir = Path("templates")
output_dir = Path("generated")
output_dir.mkdir(parents=True, exist_ok=True)

data = json.loads(feature_map_path.read_text())

env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    trim_blocks=True,
    lstrip_blocks=True
)

files_to_generate = {
    "config_pkg.vh.j2": "config_pkg.vh",
    "alu_control.v.j2": "alu_control.v",
    "control_unit.v.j2": "control_unit.v"
}
for template_name, output_name in files_to_generate.items():
    template = env.get_template(template_name)
    rendered = template.render(
        features=data["features"],
        alu_ops=data["alu_ops"],
        used_instructions=data["used_instructions"]
    )

    out_path = output_dir / output_name
    out_path.write_text(rendered + "\n")
    print(f"Wrote {out_path}")
