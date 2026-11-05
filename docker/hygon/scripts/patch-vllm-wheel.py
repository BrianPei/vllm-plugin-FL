"""Align the OpenCV requirement with vendor NumPy 1.26; preserve runtime code."""
import base64,csv,hashlib,io,json,pathlib,sys,zipfile
src=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(src) as z:
 files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
meta=next(n for n in files if n.endswith('.dist-info/METADATA'))
text=files[meta].decode();lines=text.splitlines(True);changed=0
for i,line in enumerate(lines):
 if line.startswith('Requires-Dist: opencv-python-headless'):
  lines[i]='Requires-Dist: opencv-python-headless>=4.11.0,<4.12\n';changed+=1
assert changed==1,changed
files[meta]=''.join(lines).encode();record=meta.rsplit('/',1)[0]+'/RECORD'
rows=[]
for n,b in files.items():
 if n==record:continue
 rows.append((n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).rstrip(b'=').decode(),len(b)))
rows.append((record,'',''));buf=io.StringIO();csv.writer(buf,lineterminator='\n').writerows(rows);files[record]=buf.getvalue().encode()
dest=out/src.name
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
 for n,b in files.items():z.writestr(n,b)
print(json.dumps({'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'modified':[meta,record],'output':str(dest)}))
