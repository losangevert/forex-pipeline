# Choix de robustesse et contrôles qualité

## Robustesse

1. **Retries justifiés** : Chaque tâche a un nombre de tentatives adapté à son risque.
   - `extract_raw` (2 retries) : l'appel API peut échouer transitoirement (timeout réseau, 5xx).
   - `store_raw` / `load_graveyard` (1 retry) : échec DB rare mais possible.
   - `transform_validate` (2 retries) : la logique est locale, mais on garde une marge.
   - `load_valid` (2 retries) : conflits d'insertion rattrapés via ON CONFLICT DO NOTHING.
   - `detect_anomalies` (1 retry) : requête de lookup rapide.
   - `log_pipeline` (2 retries) : doit réussir pour tracer l'exécution.

2. **Timeouts** : Chaque tâche a un timeout (`timedelta(seconds=…)`) pour éviter les bloquages.
   - Appel API : 60s max, requête HTTP : 30s.

3. **Chemins nominal et d'échec** :
   - Si l'API est injoignable → raise → retry automatique.
   - Si une ligne valide échoue à l'insertion DB → redirigée vers le cimetière.
   - Le DAG ne bloque pas sur un échec partiel.

4. **Idempotence** : `ON CONFLICT (currency_pair, rate_date, ingested_at) DO NOTHING` garantit
   qu'une re-exécution ne duplique pas les données.

5. **Configuration externalisée** : Les Variables Airflow (`forex_currencies`,
   `forex_alert_threshold`, `forex_freshness_hours`) permettent de modifier les paramètres
   sans redéployer le code.

## Contrôles qualité

| Dimension | Contrôle | Action |
|-----------|----------|--------|
| **Complétude** | Vérifie que chaque paire attendue est présente dans la réponse API | Warning log + pistage |
| **Cohérence** | Le taux est un nombre > 0 | Rejet → cimetière |
| **Fraîcheur** | La date API ne dépasse pas `freshness_hours` heures | Warning log |
| **Unicité** | Doublons gérés par contrainte UNIQUE + ON CONFLICT | Ignoré silencieusement |
| **Structure** | Vérifie présence et type de la clé `rates` dans le payload API | Exception → retry |

## Seuil d'alerte retenu : 2%

Justification : Les paires EUR/USD, EUR/GBP fluctuent typiquement de 0,1 % à 1 % par jour
sur le marché des changes. Un seuil à 2 % capte les mouvements anormaux (crise, annonce
macroéconomique) sans générer de faux positifs quotidiens. Ce seuil est configurable
via la Variable Airflow `forex_alert_threshold`.
