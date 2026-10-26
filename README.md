# Kirppari-Kalle for Home Assistant

Home Assistant -integraatio (HACS) Kirppari-Kallen myyjille: saldo, myydyt tuotteet,
myyntijakson ajat ja tapahtuma uusista myynneistä ilmoituksia varten.

## Ei virallinen / Not affiliated

**Suomeksi:** Tämä on yksityishenkilön tekemä, epävirallinen integraatio. Sillä ei ole
mitään yhteyttä Kirppari-Kalleen tai palvelun omistajaan, eikä Kirppari-Kalle ole
tehnyt, hyväksynyt, tukenut tai tarkastanut sitä. Integraatio lukee Kirppari-Kallen
web-käyttöliittymää käyttäjän omilla tunnuksilla samalla tavalla kuin selain; se ei
käytä virallista rajapintaa. Palvelun muutokset voivat rikkoa integraation milloin
tahansa. Käyttö omalla vastuulla. Älä ota yhteyttä Kirppari-Kallen asiakaspalveluun
tätä integraatiota koskevissa asioissa – käytä tämän repon issueita.

Kirppari-Kalle-nimi ja -logo ovat omistajansa tavaramerkkejä. Logoa käytetään
ainoastaan osoittamaan, mihin palveluun integraatio liittyy.

**In English:** This is an unofficial integration made by a private individual. It is
not affiliated with, endorsed, supported or reviewed by Kirppari-Kalle or its owner.
It reads the Kirppari-Kalle web interface with the user's own credentials, the same
way a browser does; it does not use an official API and may break whenever the
service changes. Use at your own risk. Please do not contact Kirppari-Kalle support
about this integration – use this repository's issues instead.

The Kirppari-Kalle name and logo are trademarks of their owner and are used only to
identify the service this integration works with.

## Asennus

1. HACS → ⋮ → *Custom repositories* → `https://github.com/quenthal/kirpparikalle-hacs`,
   tyyppi *Integration*.
2. Lataa *Kirppari-Kalle* ja käynnistä Home Assistant uudelleen.
3. *Asetukset → Laitteet ja palvelut → Lisää integraatio → Kirppari-Kalle*.
4. Anna Kirppari-Kallen myyjätunnus ja salasana. Jos tunnukseen on liitetty useita
   kirpputoreja, valitse yksi; muut voi lisätä myöhemmin omina merkintöinään.

Käytä Kirppari-Kalleen salasanaa, jota et käytä muualla: Home Assistant tallentaa sen
integraation asetuksiin (myös varmuuskopioihin) kuten muidenkin integraatioiden
salasanat. Jos salasana vaihtuu, Home Assistant pyytää kirjautumaan uudelleen.

Kuvake näkyy Home Assistant 2026.3:sta alkaen; integraatio toimii 2025.1:stä alkaen.

## Entiteetit

Jokainen kirpputori on oma laitteensa:

| Entiteetti | Kuvaus |
|---|---|
| Saldo | kokonaismyynti (EUR); provisiot vähennetään vasta tilityksessä |
| Myytyjä tuotteita | myytyjen tuotteiden määrä nykyisellä varauksella |
| Myynti alkaa / Myynti päättyy | myyntijakson ensimmäinen avaus ja viimeinen sulkeminen |
| Myyntijakso | päällä myyntijakson aikana |
| Myyntimuutos | tapahtumaentiteetti, kun saldo tai myydyt tuotteet muuttuvat |
| Tarkistettu, Tiedot päivitetty | viimeisin luku ja Kirppari-Kallen oma päivitysaika (diagnostiikka) |

Myyntejä luetaan 5 minuutin välein, kun varaus on voimassa ja kirppis auki, sekä kerran
10 minuuttia sulkemisen jälkeen. Muulloin integraatio käy sivulla kerran tunnissa, jotta
kirjautuminen pysyy voimassa. Varaukset ja aukioloajat päivitetään käynnistyksessä sekä
klo 8 ja 20. Uuden varauksen ensimmäinen luku on lähtötila, eikä Home Assistantin
uudelleenkäynnistys ilmoita jo nähtyjä myyntejä uudestaan.

## Ilmoitus uusista myynneistä

Integraatio lähettää tapahtuman `kirpparikalle_sales_update`:

```json
{"event_type": "sales_update", "shop": "Esimerkkikirppis", "entry_id": "…",
 "observed_at": "2026-10-03T12:01:29+03:00",
 "previous_balance": 16.0, "balance": 24.0, "balance_change": 8.0,
 "new_sales": [{"date": "03.10.2026", "number": 123, "name": "Esimerkkituote", "price": 8.0}],
 "removed_sales": []}
```

```yaml
alias: Kirppari-Kalle - uusi myynti
triggers:
  - trigger: event
    event_type: kirpparikalle_sales_update
conditions:
  - condition: template
    value_template: "{{ (trigger.event.data.new_sales | default([]) | count) > 0 }}"
actions:
  - action: notify.notify
    data:
      message: >-
        {% set p = trigger.event.data %}
        {{ p.shop }}: saldo {{ "%.2f"|format(p.balance | float) }} €
        (+{{ "%.2f"|format(p.balance_change | float) }} €)

        Myyty viime tarkistuksen jälkeen:
        {% for item in p.new_sales %}
        • {{ item.name }} — {{ "%.2f"|format(item.price | float) }} €
        {% endfor %}
mode: queued
max: 10
```

## Siirtyminen kirpparikalle-mqtt:stä

Integraatio on itsenäinen eikä tarvitse MQTT:tä, erillistä palvelinta tai
`kirpparikalle-mqtt`-palvelua. Ainoa yhteinen asia on Kirppari-Kallen tunnus, ja
molemmat voivat olla käytössä yhtä aikaa.

1. Asenna integraatio ja lisää kirpputori (tunnus ja salasana kuten MQTT-palvelun
   `KK_USERNAME`/`KK_PASSWORD`; `KK_SHOP` valitaan listasta). Muita asetuksia tai
   tiedostoja ei siirretä.
2. Vertaa yhden myyntijakson ajan, että saldo ja myyntimäärä täsmäävät.
3. Vaihda automaatioihin trigger `mqtt: kirpparikalle/update` →
   `event: kirpparikalle_sales_update` ja `trigger.payload_json` → `trigger.event.data`,
   ja poista MQTT-versiota käyttävät automaatiot (muuten ilmoitukset tulevat kahdesti).
4. Aja MQTT-palvelu alas ja poista sen asetustiedosto ja istuntotiedostot.

## Kehitys

```bash
python3.13 -m venv .venv
.venv/bin/pip install pytest-homeassistant-custom-component ruff
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest
```

Testit käyttävät keksittyä dataa eivätkä ota yhteyttä Kirppari-Kalleen.

Versiot: `vuosi.kuukausi.järjestysnumero` (esim. `2026.10.1`).
