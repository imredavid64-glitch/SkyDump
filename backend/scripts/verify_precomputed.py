import json
idx = json.load(open('api/precomputed/index.json'))
print('Sectors:', len(idx['sectors']))
for s in idx['sectors']:
    print(f'  {s["id"]}: {s["name"]} - {s["num_sites"]} sites, {s["total_area_m2"]:,.0f} m2')