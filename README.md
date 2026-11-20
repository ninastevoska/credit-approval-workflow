# Sistem za obravnavo kreditnih vlog

Spletna aplikacija za digitalizacijo in upravljanje procesa obravnave kreditnih vlog. Sistem omogoča oddajo interaktivnih PDF-obrazcev, samodejno preverjanje podatkov, obravnavo vlog po določenih poslovnih pravilih ter beleženje procesnih dogodkov za nadaljnjo analizo in preverjanje skladnosti procesov.

Aplikacija je razvita v **Pythonu**, z uporabo **Streamlit** za uporabniški vmesnik, **SQLite** za shranjevanje podatkov ter **pypdf** za obdelavo interaktivnih PDF-obrazcev.

## Funkcionalnosti

- Oddaja kreditnih vlog prek interaktivnih PDF-obrazcev.
- Samodejno branje in validacija podatkov iz PDF-ja.
- Upravljanje vlog glede na uporabniško vlogo: stranka, referent ali vodja.
- Prevzem, pregled in bonitetno ocenjevanje kreditnih vlog.
- Odobritev ali zavrnitev kreditne vloge.
- Posredovanje vlog nad 20.000 EUR vodji v odločanje.
- Zahtevanje dopolnitve dokumentacije in ponovni pregled.
- Samodejno izvajanje določenih procesnih aktivnosti.
- Evidentiranje petih prednastavljenih vrst ročnih dogodkov in poljubno poimenovanih dogodkov.
- Način brez omejitev, ki omogoča odstopanja od predpisanega procesa.
- Beleženje aktivnosti v dnevnik dogodkov in izvoz v CSV.
- Shranjevanje podatkov v SQLite z ohranjanjem zgodovine dogodkov.

## Procesne poti

Sistem podpira pet procesnih poti:

1. **Neposredna odobritev:** oddaja → samodejno preverjanje → prevzem → pregled → ocena kreditne sposobnosti → odobritev referenta → obveščanje.
2. **Dopolnitev in odobritev:** oddaja → preverjanje → prevzem → pregled → zahteva za dopolnitev → oddaja dopolnjenega PDF-ja → ponovni pregled → ocena → odobritev → obveščanje.
3. **Zavrnitev referenta:** oddaja → preverjanje → prevzem → pregled → ocena kreditne sposobnosti → zavrnitev referenta → obveščanje.
4. **Odobritev vodje:** oddaja → preverjanje → prevzem → pregled → ocena kreditne sposobnosti → posredovanje vodji → pregled vodje → odobritev → obveščanje.
5. **Zavrnitev vodje:** oddaja → preverjanje → prevzem → pregled → ocena kreditne sposobnosti → posredovanje vodji → pregled vodje → zavrnitev → obveščanje.

Referent lahko neposredno odobri kreditne vloge do vključno **20.000 EUR** z bonitetno oceno A ali B. Za vloge nad tem pragom je pristojen vodja, ki lahko vlogo odobri ali zavrne.

### Ročni dogodki in način brez omejitev

Referent lahko med obravnavo evidentira telefonski klic stranki, poslano ali prejeto e-pošto, posvet s sodelavcem in posvet z vodjo. Doda lahko tudi poljubno poimenovan dogodek.

Način brez omejitev omogoča izvajanje določenih aktivnosti mimo običajnih pravil, na primer odobritev vloge nad pristojnostjo referenta ali preskok pregleda. Takšna dejanja se prav tako zabeležijo v dnevnik dogodkov z dejanskim izvajalcem.

## Struktura projekta

```text
credit-approval-workflow/
├── app.py
├── config.py
├── database.py
├── models.py
├── requirements.txt
├── README.md
├── dnevnik.csv
├── services/
│   ├── application_service.py
│   ├── event_service.py
│   ├── file_service.py
│   ├── pdf_form_service.py
│   ├── verification_service.py
│   └── workflow_service.py
├── ui/
│   ├── components.py
│   ├── customer_view.py
│   ├── referent_view.py
│   └── manager_view.py
├── scripts/
│   └── generate_pdf_forms.py
├── forms/
│   ├── kreditna_vloga_predloga.pdf
│   ├── kreditna_vloga_popolna.pdf
│   ├── kreditna_vloga_nepopolna.pdf
│   └── ...
├── tests/
│   └── ...
└── data/
    └── uploads/
```

## Namestitev

Potrebujete **Python 3.12 ali novejši**.

**1. Kloniranje repozitorija**

```powershell
git clone https://github.com/ninastevoska/credit-approval-workflow.git
cd credit-approval-workflow
git switch feature/process-governance
```

**2. Ustvarjanje in aktivacija virtualnega okolja (Windows PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**3. Namestitev odvisnosti**

```powershell
python -m pip install -r requirements.txt
```

## Zagon aplikacije

```powershell
python -m streamlit run app.py
```

Aplikacija je dostopna na naslovu:

http://localhost:8501

## Interaktivni PDF-obrazci

Mapa `forms/` vsebuje prazno predlogo ter izpolnjene testne obrazce za različne procesne poti.

Obrazec vsebuje naslednja polja:

- `zaprosen_znesek` – zaprošeni znesek kredita v EUR.
- `namen_kredita` – namen kredita (spustni seznam).
- `mesecni_prihodek` – mesečni prihodek v EUR.

Stranka izpolni in shrani obrazec ter ga naloži v aplikacijo. Sistem podatke samodejno prebere in preveri, zato ponovni vnos v spletni obrazec ni potreben.

Predlogo in testna obrazca je mogoče ponovno ustvariti z ukazom:

```powershell
python scripts/generate_pdf_forms.py
```

## Dnevnik dogodkov

Vsaka izvedena aktivnost se zabeleži z identifikatorjem primera, časovno oznako, izvajalcem, vlogo, statusom in pripadajočimi atributi.

Dnevnik vključuje tudi ročno evidentirane dogodke ter aktivnosti, izvedene v načinu brez omejitev.

Podatki se hranijo v SQLite, izvoz CSV pa omogoča nadaljnjo analizo in rudarjenje procesov.

Datoteka `dnevnik.csv` vsebuje zabeležene procesne dogodke.

## BPMN-model

Predpisani proces obravnave kreditnih vlog je predstavljen z modelom **BPMN 2.0** v datoteki `credit_approval_process.bpmn`.

Model vključuje vseh pet procesnih poti, sodelujoče vloge, odločitvena vrata ter aktivnosti obveščanja. Namenjen je nadaljnjemu preverjanju skladnosti med predpisanim in dejansko izvedenim procesom.


## Testiranje

Za zagon vseh avtomatskih testov uporabite:

```powershell
python -m pytest -q
```

Testi preverjajo poslovna pravila, pristojnosti uporabnikov, procesne prehode, validacijo PDF-obrazcev, shranjevanje podatkov, dnevnik dogodkov, način brez omejitev in različne procesne poti.