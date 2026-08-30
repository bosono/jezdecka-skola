# Jezdecká škola — CRM · návrh

Datum: 2026-08-30
Stav: fáze 1 (náhled) hotová, schváleno

## Cíl

Nástroj pro plánování lekcí jezdecké školy. Tři stavební kameny:
kartotéka jezdců, kartotéka koní s hlídáním vytíženosti, a týdenní rozvrh
lekcí s drag&drop párováním jezdec–kůň.

## Rozhodnutí

| Téma | Volba |
|------|-------|
| Nasazení | Web aplikace na serveru |
| Přístup | Jedno sdílené heslo, session cookie |
| Umístění | `~/Documents/Claude/jezdecka-skola` |
| Stack | Fáze 1: samostatné HTML + localStorage. Fáze 2: Python + Flask + SQLite |
| Rozvrh | Týdenní šablona + výjimky na konkrétní datum |
| Vytíženost koně | Lekcí/den, lekcí/týden, hodin/týden + povinné dny volna |
| Úroveň jezdce | Začátečník / Pokročilý / Závodník |
| Kapacita lekce | Skupinová až N jezdců, každý svůj kůň |
| Preferovaný kůň | Jen nápověda při párování, ne pravidlo |
| Kontroly | Měkká varování; tvrdý blok jen časová kolize |

## Datový model

- **rider**: jméno, kontakt, úroveň (`zacatecnik|pokrocily|zavodnik`),
  preferovaní koně (seznam odkazů, nezávazné), poznámka, aktivní.
- **horse**: jméno, popis, povolené disciplíny (skup/kaval/komb/skok),
  max lekcí/den, max lekcí/týden, max hodin/týden, dny volna, poznámka, aktivní.
- **lesson_type**: skupinové, kavalety, kombinovaná, skoková; atribut „min. úroveň".
- **lesson_slot** (šablona): den v týdnu, čas od–do, typ, trenér, kapacita, místo.
- **lesson_assignment**: slot × rider × horse.
- **schedule_exception** (fáze 2): datum, slot, akce (přesun / zrušení / přidání).

## Obrazovky

1. **Jezdci** — tabulka + filtr úrovně + hledání; detail/editace v modálu;
   badge „lekcí tento týden".
2. **Koně** — tabulka s ukazatelem vytížení (lekcí i hodiny vs. limit, barevně);
   detail/editace v modálu.
3. **Rozvrh** — týdenní mřížka den × čas. Panel „jezdci" + „koně" k přetažení.
   Přetažení jezdce do slotu vytvoří dvojici, appka navrhne volného vhodného koně
   (preferovaný > jakýkoli povolený, ne v den volna, ne obsazený).
   Přidání slotu kliknutím do volné buňky.

## Kontroly při přiřazení

Měkká varování (žlutě, nebrání uložení):
- jezdec má nižší úroveň, než typ lekce vyžaduje;
- kůň nemá povolenou disciplínu daného typu;
- kůň má v ten den volno;
- kůň by překročil denní / týdenní limit lekcí nebo limit hodin.

Tvrdý blok (červeně):
- jezdec nebo kůň už má ve stejném čase jinou lekci (časová kolize).

## Mimo rozsah (YAGNI)

Fakturace, docházka a platby, e-maily klientům, mobilní appka,
historie výkonnosti jezdce, více stájí/poboček, role a účty trenérů.

## Fázování

1. **Náhled** — `index.html`, localStorage, žádný backend. *(hotovo)*
2. **Backend** — Flask + SQLite, sdílené heslo, výjimky z rozvrhu.
3. **Nasazení** — GitHub (příp. účet Bosono) + hosting.
