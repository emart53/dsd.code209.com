import csv, re, os
from decimal import Decimal, InvalidOperation
from datetime import datetime
from dsd.models import Vendor, LinkGroup, Item, PendingCostChange, ChangeHistory

CSV_PATH = '/home/codeeqid/dsd.code209.com/DSD_Master_-_Master.csv'

VENDOR_NAMES = {
    "33CRAF":"33 Craft Spirits","7UP":"7UP Bottling Company","AC FOO":"AC Food",
    "AM BRE":"American Breads","AM CRE":"American Creameries","ANIMSU":"Animas Universal",
    "BIMBO":"Bimbo Bakeries","BRKTHR":"Breakthrough Beverages","BUD":"Anheuser-Busch/Budweiser",
    "CALSUN":"California Sun Dry","CAMPOS":"Campos Brothers","CAZODO":"Casa Zodo",
    "CLASSC":"Classic Foods","COKE":"Coca-Cola Bottling","CRYSTL":"Crystal Creamery",
    "DONSAL":"Don Salvador","EL KOR":"El Kora","ELMEXI":"El Mexicano",
    "FERNDS":"Fernandez Foods","FRITO":"Frito-Lay Inc.","GALLO":"E&J Gallo Winery",
    "GIBSON":"Gibson Wine Company","GLDRSH":"Goldenrod Farms","GOYA":"Goya Foods",
    "GRANDA":"Granada Foods","GVALLY":"Gold Valley","JACENT":"Jacent Strategic Merch.",
    "JGI":"JGI Foods","JOSEPH":"Joseph Farms","LAPERL":"La Perla","LAROSA":"La Rosa",
    "LATAPA":"La Tapatia","LATORT":"La Tortilla Factory","MARTIN":"Martins Famous Pastry",
    "MCKEE":"McKee Foods/Little Debbie","MERCLT":"Mercado Latino",
    "MILLER":"Miller Brewing/MillerCoors","MINISN":"Mini Snacks","MISSN":"Mission Foods",
    "MONTER":"Monterey Mushrooms","NABSCO":"Nabisco/Mondelez","NESTLE":"Nestle USA",
    "NOBLE":"Noble Juice","NORCAL":"NorCal Beverage","NUCAL":"NuCal Foods",
    "NUTCH":"Nutchel Foods","OLIVET":"Oliveto Foods","OLIVRA":"Olivera Foods",
    "PEERLE":"Peerless Coffee","PEETS":"Peets Coffee","PEPES":"Pepes Foods",
    "PEPSI":"PepsiCo Beverages","PFARMS":"Pacific Farms","PHOENI":"Phoenix Foods",
    "PRDCRS":"Producers Dairy","REDBLL":"Red Bull North America","REYNA":"Reyna Foods",
    "RNDC":"Republic National Dist.","ROPAME":"Ropa Americana","ROSABR":"Rosa Brand",
    "ROSIE":"Rosie Foods","RUGDO":"Rugido Foods","SANTOS":"Santos Foods",
    "SNYDER":"Snyders-Lance","SOPAC":"So-Pac Distributing","STHRN":"Southern Wine & Spirits",
    "T&S":"T&S Foods","THAL G":"Thal G Foods","TLTECA":"Tolteca Foods",
    "TONYS":"Tonys Fine Foods","TROPIC":"Tropical Foods","USTRAD":"US Trading",
    "VALEYW":"Valley Wholesale","WONDER":"Wonder/Flowers Baking",
}

def money(v):
    if not v: return Decimal("0.00")
    c = re.sub(r"[^0-9.-]","",str(v))
    try: return Decimal(c).quantize(Decimal("0.01"))
    except: return Decimal("0.00")

def pdate(v):
    if not v or not str(v).strip(): return None
    try:
        p = str(v).strip().split("/")
        if len(p)==3:
            m,d,y = int(p[0]),int(p[1]),int(p[2])
            if y<100: y+=2000
            return datetime(y,m,d).date()
    except: pass
    return None

def pint(v,d=1):
    try: return max(1,int(float(str(v)))) if v and str(v).strip() else d
    except: return d

def pint_none(v):
    try: return int(float(str(v))) if v and str(v).strip() else None
    except: return None

def istrue(v):
    return str(v).strip().upper() in ("Y","YES","1","TRUE","X","T") if v else False

print("Clearing data...")
PendingCostChange.objects.all().delete()
ChangeHistory.objects.all().delete()
Item.objects.all().delete()
LinkGroup.objects.all().delete()
Vendor.objects.all().delete()
print("Cleared.\n")

vc, lgc, buf = {}, {}, []
stats = dict(v=0, lg=0, i=0, sk=0, err=0)

def flush():
    if not buf: return
    try:
        Item.objects.bulk_create(buf, ignore_conflicts=True)
        stats["i"] += len(buf)
        print(f"  ... {stats['i']} items")
    except Exception as e:
        print(f"  ERR: {e}")
        stats["err"] += len(buf)
    buf.clear()

with open(CSV_PATH, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        v = row.get("Vendor Code","").strip()
        if not v or v=="#REF!":
            stats["sk"] += 1
            continue

        if v not in vc:
            obj = Vendor.objects.create(
                vendor_code=v,
                vendor_name=VENDOR_NAMES.get(v, v),
                comm_method="EXCEL",
                target_margin=Decimal("0.2800"),
            )
            vc[v] = obj
            stats["v"] += 1
            print(f"  {v} - {obj.vendor_name}")

        lc = row.get("Link Code","").strip()
        lg = None
        if lc:
            k = f"{v}|{lc}"
            if k not in lgc:
                lgc[k] = LinkGroup.objects.create(
                    vendor=vc[v], link_code=lc,
                    link_group_name=row.get("Link Group Name","").strip() or lc,
                )
                stats["lg"] += 1
            lg = lgc[k]

        upc = re.sub(r"[^0-9]","",str(row.get("UPC","")).strip())
        if not upc:
            stats["sk"] += 1
            continue

        cc    = money(row.get("Case Cost",""))
        net   = money(row.get("Net Case Cost",""))
        allow = (cc - net).quantize(Decimal("0.01")) if net > 0 and net < cc else Decimal("0.00")
        lcd   = pdate(row.get("Last Change Date",""))

        buf.append(Item(
            vendor=vc[v], upc=upc,
            seq=pint_none(row.get("SEQ","")),
            link_group=lg,
            brdata_item_no=row.get("Vendor #","").strip()[:20] or None,
            description=row.get("Long Description","").strip()[:100],
            case_pack=pint(row.get("Case Pack",""),1),
            size_alpha=row.get("Size Alpha","").strip()[:20] or None,
            case_cost=cc,
            allowance=allow,
            price_qty=pint(row.get("Price Qty",""),1),
            retail_price=money(row.get("Price","")) or None,
            last_cost_change=lcd,
            last_price_change=lcd,
            is_disco=istrue(row.get("Disco","")),
            is_tpr=istrue(row.get("TPR","")),
            movement=pint_none(row.get("Movement","")),
            vendor_comments=row.get("Vendor Comments","").strip()[:500] or None,
            notes=row.get("NOTES","").strip()[:500] or None,
            is_active=True,
        ))

        if len(buf) >= 500:
            flush()

flush()

print(f"\nVendors:{stats['v']} LinkGroups:{stats['lg']} Items:{stats['i']} Skipped:{stats['sk']} Errors:{stats['err']}")
print(f"DB: Vendors:{Vendor.objects.count()} Items:{Item.objects.count()} Dated:{Item.objects.filter(last_cost_change__isnull=False).count()}")
