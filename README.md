# Analýza Spotify dat

Nástroj pro lokální analýzu a vizualizaci dat z "Extended Streaming History" od Spotify. Skript zpracovává .json soubory, provádí statistické výpočty a generuje samostatný HTML report.

## Funkce
- Statistiky: Celková doba poslechu, počet unikátních skladeb a umělců.
- Detekce vzorců: 
    - Identifikace často přeskakovaných skladeb.
    - Analýza "binge listening" (opakované přehrávání stejné skladby).
    - Vyhledávání dříve velmi oblíbených skladeb, které už dnes neposloucháte ("Hidden Gems").
- Vizualizace: 
    - Roční vývoj poslechovosti.
    - Denní rytmus poslechu.
- Report: Kompletní dashboard v HTML formátu.

## Požadavky
Python 3.x a knihovny pandas, numpy. Instalace:

pip install pandas numpy

## Použití
1. Získejte data ze svého účtu Spotify (sekce Download your data -> Extended streaming history).
2. Vložte stažené .json soubory do složky ./data.
3. Spusťte skript:

python run.py

4. Výsledný report otevřete v prohlížeči souborem output.html.

## Bezpečnost
Skript běží lokálně. Žádná data nejsou odesílána ven.