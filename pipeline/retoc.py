import re, subprocess, json
SOFF="/root/.claude/skills/synced/acdb1813-79f3-44d2-8e4e-caeb82a9f2a2_b9d47771-7223-4d8b-a0f5-101fa15f6609/docx/scripts/office/soffice.py"
def build():
    subprocess.run(["node","make_doc.js"],check=True,capture_output=True)
    subprocess.run(["python3",SOFF,"--headless","--convert-to","pdf","Pseudoword_Generator_documentation.docx"],capture_output=True)
for it in range(2):
    src=open("make_doc.js").read()
    body_src=src[src.index("const body = ["):]
    heads=re.findall(r'\b(H1|H2)\("([^"]+)"\)', body_src)
    i=[k for k,(l,t) in enumerate(heads) if t.startswith("Appendix B")][0]
    heads[i+1:i+1]=[("H2","B.1 Data, methods and software (annotated; from SOURCES.md)"),("H2","B.2 Orthography descriptions used for the grapheme inventories")]
    build()
    n=int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo","Pseudoword_Generator_documentation.pdf"],capture_output=True,text=True).stdout).group(1))
    pages=[re.sub(r"\s+"," ",subprocess.run(["pdftotext","-f",str(i),"-l",str(i),"Pseudoword_Generator_documentation.pdf","-"],capture_output=True,text=True).stdout) for i in range(1,n+1)]
    toc=[]; last=3
    for lvl,t in heads:
        short=t[:45]
        pg=next((i+1 for i,p in enumerate(pages) if i+1>=last and short in p), None)
        if pg is None: pg=last
        last=pg; toc.append([lvl,t,pg])
    src=re.sub(r"const TOC = \[.*?\];", "const TOC = "+json.dumps(toc, ensure_ascii=False)+";", src, count=1, flags=re.S)
    open("make_doc.js","w").write(src)
build()
print(n, toc)
