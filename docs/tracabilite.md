# Matrice de traçabilité : exigences → composants → tests

Chaque exigence du cahier des charges (objectifs O, livrables L) et chaque contrainte du prompt maître (C) est reliée aux composants qui la réalisent et aux tests qui la vérifient. La colonne **Statut** est mise à jour à chaque fin de phase. Le détail des exigences (`EX-…`) est dans `docs/L1_specifications.md` (sections 1 et 11) ; les noms de tests sont prévisionnels. Les composants et tests du tableau détaillé sont recopiés de L1 ; `tests/test_specifications.py` vérifie la cohérence des deux documents. Chemins relatifs à `src/amundi_agentic/`, sauf ceux qui commencent par un dossier racine (`config/`, `app/`, `agent_prompts/`, `runs/`).

## Objectifs du cahier des charges

| ID | Exigence | Exigences détaillées | Composants | Phase | Statut |
| --- | --- | --- | --- | --- | --- |
| O1 | Agents qui recommandent à partir d'analyses quantitatives et qualitatives | EX-O1-01 à EX-O1-17 | `agents/`, `tools/`, `debate/`, `schemas.py`, `agent_prompts/`, `cli.py`, `data/quality.py` | 2, 3 | Spécifié |
| O2 | Portefeuilles optimisés sous contraintes de risque, de diversification et d'objectifs client | EX-O2-01 à EX-O2-12 | `portfolio/`, `data/connectors/fx.py`, `data/universe.py`, `config/profiles.yaml`, `config/esg.yaml` | 2, 4 | Spécifié |
| O3 | Mise à jour et ajustement automatiques | EX-O3-01 à EX-O3-09 | `rebalancing/`, `config/costs.yaml` | 4, 5 | Spécifié |
| O4 | Transparence et explicabilité | EX-O4-01 à EX-O4-08 | `debate/journal.py`, `explain/`, `app/` | 3, 6, 7 | Spécifié |
| O5 | Évaluation face à des benchmarks traditionnels | EX-O5-01 à EX-O5-13 | `evaluation/` | 7 | Spécifié |

## Exigences détaillées O1 à O5

| ID | Exigence (résumé) | Composants | Tests prévus | Phase | Statut |
| --- | --- | --- | --- | --- | --- |
| EX-O1-01 | Vues par classe (Macro, Valuation/Momentum, Sentiment) ; alertes de l'agent Risque par seuils Python | `agents/macro.py`, `agents/valuation.py`, `agents/sentiment.py`, `agents/risk.py`, `tools/risk.py`, `schemas.py` | `test_agents_allocation_produisent_des_vues_valides` (LLM simulé : une vue valide par classe et par agent) ; `test_alertes_risque_calculees_par_seuils_python` (le LLM ne peut pas modifier une alerte) | 3 | Prévu |
| EX-O1-02 | Vues par titre (Fundamental, Sentiment, Valuation) | `agents/fundamental.py`, `agents/sentiment.py`, `agents/valuation.py` | `test_agents_titres_produisent_des_vues_valides` | 3 | Prévu |
| EX-O1-03 | Sources obligatoires, antérieures à la coupure de t ; sorties d'outils datées | `schemas.py` (validateurs de `View` et `Source`) | `test_vue_sans_source_rejetee` ; `test_source_posterieure_a_t_rejetee` ; `test_vue_sans_argument_contre_rejetee` ; `test_sortie_outil_datee_par_sa_derniere_donnee` | 3 | Prévu |
| EX-O1-04 | Chiffres calculés par les outils, contrôle d'ancrage | `tools/finance.py`, `tools/risk.py`, `tools/macro_regime.py`, `agents/base.py` (contrôle d'ancrage) | `test_rendement_et_volatilite_annualises_formules_du_papier` ; `test_valuation_appelle_ses_outils` (trace d'appels d'outils) ; `test_chiffre_absent_des_outils_signale` | 3 | Prévu |
| EX-O1-05 | Rendement excédentaire (décimal) calculé depuis le niveau, jamais par le LLM | `portfolio/views.py` | `test_niveau_vers_rendement_excedentaire_monotone` ; `test_champ_rendement_rempli_par_l_outil_pas_par_le_llm` | 3, 4 | Prévu |
| EX-O1-06 | Prompts de rôle versionnés et hashés | `agents/prompts.py`, `agent_prompts/` | `test_prompts_charges_depuis_fichiers_et_hashes` ; `test_aucun_prompt_de_role_dans_le_code` | 3 | Prévu |
| EX-O1-07 | Débat borné, consensus calculé, statut contesté | `debate/orchestrator.py`, `debate/consensus.py` | `test_debat_termine_en_au_plus_rmax_tours` ; `test_consensus_unanime_arrete_le_debat` ; `test_vue_contestee_arbitree_par_coordinateur` ; `test_vue_contestee_niveau_borne_a_un` | 3 | Prévu |
| EX-O1-08 | Avocat du diable tournant | `debate/devil.py` | `test_avocat_du_diable_tourne_entre_les_tours` ; `test_sortie_avocat_contient_une_objection_sourcee` | 3 | Prévu |
| EX-O1-09 | Décision à 5 niveaux | `schemas.py` (`Decision5`) | `test_decision_cinq_niveaux_valeurs_admises` | 3 | Prévu |
| EX-O1-10 | Exclusions ESG avant recommandation, veto | `agents/esg.py`, `data/connectors/esg.py`, `config/esg.yaml` | `test_titre_exclu_jamais_debattu_ni_recommande` ; `test_veto_esg_motive_et_journalise` | 2, 3 | Prévu |
| EX-O1-11 | Profil de risque dans le prompt | `agents/base.py` | `test_profil_injecte_dans_le_prompt` | 3 | Prévu |
| EX-O1-12 | Une commande produit vues et rapport d'une date | `cli.py` | `test_cli_analyse_une_date_avec_llm_simule` (intégration) | 3 | Prévu |
| EX-O1-13 | Réplication AlphaAgents : graine hashée, remplacement fixé, résultats « contaminés » | `evaluation/replication.py`, `config/replication.yaml` | `test_configuration_replication_conforme_au_papier` ; `test_graine_hashee_avant_tirage` ; `test_regle_de_remplacement_deterministe` ; comparaison qualitative `[llm]` | 3 | Prévu |
| EX-O1-14 | RAG par section, dépôts antérieurs à t ; XBRL sans retraitement postérieur | `tools/rag.py`, `data/connectors/filings.py` | `test_rag_decoupe_par_section` ; `test_rag_ne_sert_que_les_depots_avant_t` ; `test_xbrl_valeur_connue_a_t_sans_retraitement_posterieur` ; évaluation fidélité et pertinence (Phoenix ou Ragas) `[llm]` | 2, 3 | Prévu |
| EX-O1-15 | Résumé avec réflexion | `tools/summarize.py` | `test_resume_reflexion_produit_les_trois_etapes` (LLM simulé) | 3 | Prévu |
| EX-O1-16 | Agents limités à `as_of(t)` | `data/pit.py`, `agents/base.py` | `test_agents_n_accedent_qu_a_la_vue_as_of` ; `test_aucune_donnee_posterieure_a_t` (prix, news, dépôts, macro) | 2, 3 | Prévu |
| EX-O1-17 | Couverture des news mesurée ; Sentiment retiré du backtest sous le seuil | `data/quality.py`, `agents/sentiment.py` | `test_couverture_news_par_actif_et_date` ; `test_sentiment_desactive_si_couverture_insuffisante` | 2, 3 | Prévu |
| EX-O2-01 | Σ Ledoit-Wolf (cible identité) hebdomadaire en EUR, avant t ; 260 semaines minimum | `portfolio/covariance.py` | `test_covariance_ledoit_wolf_definie_positive` ; `test_covariance_n_utilise_que_des_donnees_avant_t` ; `test_shrinkage_egal_a_l_implementation_de_reference` ; `test_actif_sans_historique_suffisant_exclu` | 4 | Prévu |
| EX-O2-02 | Π = δ Σ w_benchmark | `portfolio/black_litterman.py` | `test_prior_equilibre_formule` | 4 | Prévu |
| EX-O2-03 | Ω d'Idzorek ; monotonie de la confiance, TE inactive et active | `portfolio/views.py`, `portfolio/black_litterman.py`, `portfolio/optimizer.py` | `test_omega_idzorek_forme_fermee` ; `test_vue_plus_confiante_deplace_davantage_les_poids` ; `test_monotonie_confiance_te_inactive` (écart strictement croissant) ; `test_monotonie_confiance_te_active` (écart croissant au sens large) | 4 | Prévu |
| EX-O2-04 | Sans vue, retour au benchmark | `portfolio/black_litterman.py`, `portfolio/optimizer.py` | `test_sans_vue_retour_au_benchmark` (par profil, avec w_prev = w_b ou coûts nuls, puisque la pénalité de coût et la rotation retiennent sinon l'ancien portefeuille) | 4 | Prévu |
| EX-O2-05 | Contraintes CT-01 à CT-10 vérifiées à chaque solution | `portfolio/optimizer.py`, `portfolio/constraints.py` | Un test par contrainte : `test_contrainte_budget`, `test_contrainte_long_only`, `test_contrainte_bornes_par_actif`, `test_contrainte_bornes_par_classe`, `test_contrainte_exclusions_esg`, `test_contrainte_score_esg_minimal`, `test_contrainte_volatilite_plafond`, `test_contrainte_tracking_error`, `test_contrainte_rotation`, `test_contrainte_poche_titres` ; `test_verification_post_solution_signale_une_violation` | 4 | Prévu |
| EX-O2-06 | Profils en configuration, benchmark admissible | `portfolio/profiles.py`, `config/profiles.yaml` | `test_profils_charges_depuis_la_config` ; `test_benchmark_admissible_pour_son_profil` | 4 | Prévu |
| EX-O2-07 | Relâchement ordonné, ESG jamais relâché | `portfolio/optimizer.py` | `test_infaisabilite_relachement_ordonne` ; `test_contraintes_esg_jamais_relachees` | 4 | Prévu |
| EX-O2-08 | Méthodes de comparaison équitables (mêmes contraintes, même risque) | `portfolio/baselines.py` | `test_equiponderation_des_vues_positives` ; `test_un_sur_n_sur_les_classes_seulement` ; `test_markowitz_q_si_vue_pi_sinon` ; `test_parite_de_risque_contributions_egales` ; `test_methodes_de_comparaison_sous_memes_contraintes` ; `test_variante_meme_risque_ex_ante` | 4 | Prévu |
| EX-O2-09 | Couverture ESG mesurée et publiée | `portfolio/constraints.py`, `explain/sheet.py` | `test_couverture_esg_calculee_et_publiee` | 4 | Prévu |
| EX-O2-10 | Rendements en EUR ; pas de proxy USD pour obligations et monétaire ; jonctions publiées | `data/connectors/fx.py`, `data/universe.py` | `test_conversion_eur_cours_bce_point_in_time` ; `test_pas_de_proxy_usd_pour_obligations_et_monetaire` ; `test_dates_de_jonction_publiees` | 2 | Prévu |
| EX-O2-11 | Fréquence d'activation des contraintes publiée | `portfolio/constraints.py`, `evaluation/report.py` | `test_frequence_activation_des_contraintes_publiee` | 4, 7 | Prévu |
| EX-O2-12 | Monétaire résiduel (hors vues et hors Σ) ; plancher de volatilité des vues | `portfolio/views.py`, `portfolio/covariance.py`, `portfolio/optimizer.py` | `test_monetaire_hors_vues_et_hors_sigma` ; `test_plancher_de_volatilite_des_vues` | 4 | Prévu |
| EX-O3-01 | Revue mensuelle | `rebalancing/scheduler.py` | `test_calendrier_mensuel_premier_jour_ouvre` | 5 | Prévu |
| EX-O3-02 | Déclencheurs dérive (5/25 avec poids minimal), vue, régime | `rebalancing/triggers.py` | `test_declencheur_derive_regle_5_25` ; `test_derive_relative_ignoree_sous_poids_minimal` ; `test_declencheur_changement_de_vue` ; `test_declencheur_regime_de_volatilite` (chacun isolément) | 5 | Prévu |
| EX-O3-03 | Coûts, dont coût de change, toujours déduits | `rebalancing/costs.py`, `config/costs.yaml` | `test_couts_deduits_de_la_performance` ; `test_cout_nul_si_aucune_transaction` ; `test_cout_de_change_sur_proxys_usd` | 5 | Prévu |
| EX-O3-04 | Rotation limitée, petits ordres ignorés | `portfolio/constraints.py`, `rebalancing/proposal.py` | `test_rotation_respectee` ; `test_ordres_sous_le_seuil_ignores` | 4, 5 | Prévu |
| EX-O3-05 | Cause de chaque proposition | `rebalancing/proposal.py` | `test_chaque_proposition_a_au_moins_une_cause` | 5 | Prévu |
| EX-O3-06 | File de validation | `rebalancing/validation.py` | `test_file_validation_transitions_autorisees` ; `test_modification_reverifie_les_contraintes` ; `test_proposition_rejetee_ne_modifie_pas_le_portefeuille` | 5 | Prévu |
| EX-O3-07 | Simulation ≥ 3 ans avec causes | `evaluation/backtest.py`, `rebalancing/` | `test_simulation_trois_ans_historique_avec_causes` (données synthétiques, vues simulées) | 5 | Prévu |
| EX-O3-08 | Journal des décisions en ajout seul | `rebalancing/journal.py` | `test_journal_des_decisions_ajout_seul` | 5 | Prévu |
| EX-O3-09 | Décision à la coupure de t, exécution à la clôture de t | `rebalancing/proposal.py`, `evaluation/backtest.py` | `test_execution_a_la_cloture_de_t` ; `test_decision_n_utilise_pas_la_cloture_de_t` | 5 | Prévu |
| EX-O4-01 | Journal de débat complet | `debate/journal.py` | `test_journal_de_debat_complet` (tous les champs requis présents) | 3 | Prévu |
| EX-O4-02 | Fiche « pourquoi ce poids » | `explain/sheet.py` | `test_fiche_relie_chaque_ecart_aux_vues` | 6 | Prévu |
| EX-O4-03 | Attribution qui somme à l'écart | `explain/attribution.py` | `test_attribution_somme_a_l_ecart` ; `test_sans_contrainte_active_effet_contraintes_nul` | 6 | Prévu |
| EX-O4-04 | Version client | `explain/client_summary.py` | `test_version_client_avertissement_et_sans_identifiants` | 6 | Prévu |
| EX-O4-05 | Tableau de bord, poids → vues → sources en deux clics | `app/` | `test_app_navigation_poids_vues_sources` (`streamlit.testing.AppTest`) ; test d'usage avec au moins 2 personnes (manuel, retours notés dans `docs/`) | 6 | Prévu |
| EX-O4-06 | Contestation d'une vue tracée | `debate/orchestrator.py`, `app/` | `test_contestation_enregistree_et_tracee` ; `test_surcharge_manuelle_de_vue_marquee_comme_telle` | 6 | Prévu |
| EX-O4-07 | Chiffres des fiches issus des données | `explain/sheet.py` | `test_chiffres_de_la_fiche_issus_des_donnees` | 6 | Prévu |
| EX-O4-08 | Avertissement dans l'interface et les rapports | `app/`, `evaluation/report.py` | `test_interface_porte_l_avertissement` ; `test_rapports_portent_l_avertissement` | 6, 7 | Prévu |
| EX-O5-01 | Walk-forward mensuel avec coûts | `evaluation/backtest.py` | `test_walk_forward_sans_fuite` (à chaque pas, aucune donnée postérieure à t) ; `test_backtest_deduit_les_couts` | 7 | Prévu |
| EX-O5-02 | Métriques | `evaluation/metrics.py` | `test_metriques_valeurs_calculees_a_la_main` (une assertion par métrique, séries synthétiques) | 7 | Prévu |
| EX-O5-03 | Comparaison par profil | `evaluation/backtest.py`, `portfolio/baselines.py` | `test_rapport_compare_toutes_les_methodes_par_profil` | 7 | Prévu |
| EX-O5-04 | Ablations, dont confiance constante et profil hors prompt | `evaluation/ablations.py` | `test_configurations_d_ablation_generees` ; `test_ablation_sans_debat_saute_les_tours` ; `test_ablation_confiance_constante` | 7 | Prévu |
| EX-O5-05 | Robustesse : bootstrap par blocs, paraphrases, température > 0, Holm | `evaluation/robustness.py` | `test_bootstrap_par_blocs_stationnaire` ; `test_bootstrap_couvre_une_valeur_connue` (synthétique) ; `test_variance_des_decisions_sur_plusieurs_executions` ; `test_correction_de_holm` | 7 | Prévu |
| EX-O5-06 | Fin d'entraînement par modèle servi, étiquette « contaminé », anonymisation | `evaluation/lookahead.py`, `config/llm.yaml` | `test_fin_entrainement_relevee_pour_chaque_modele_servi` ; `test_resultats_anterieurs_a_la_fin_entrainement_etiquetes_contamines` ; `test_anonymisation_masque_noms_et_dates` ; `test_anonymisation_prix_rebases_a_cent` | 7 | Prévu |
| EX-O5-07 | Live test figé | `evaluation/live.py` | `test_decision_live_figee_hash_immuable` ; `test_decision_live_posterieure_refusee` | 7 | Prévu |
| EX-O5-08 | Rapport L4 généré, tracé, déclarant son objet | `evaluation/report.py` | `test_rapport_l4_genere_et_chiffres_traces` ; `test_rapport_l4_declare_son_objet` | 7 | Prévu |
| EX-O5-09 | Qualité du raisonnement | `evaluation/reasoning.py` | `test_part_des_affirmations_sourcees` ; grille dans `docs/` | 7 | Prévu |
| EX-O5-10 | Coût LLM par décision | `evaluation/metrics.py`, `llm/records.py` | `test_cout_llm_par_decision_agrege_les_executions` | 7 | Prévu |
| EX-O5-11 | Effet minimal détectable publié | `evaluation/robustness.py` | `test_effet_minimal_detectable_formule` | 7 | Prévu |
| EX-O5-12 | Pré-enregistrement hashé avant évaluation | `evaluation/preregistration.py`, `runs/` | `test_evaluation_refusee_sans_preregistrement` ; `test_parametres_differents_du_preregistrement_refuses` | 7 | Prévu |
| EX-O5-13 | Calibration (Brier) et unanimité au tour 0 | `evaluation/reasoning.py` | `test_score_de_brier_calcule` ; `test_taux_unanimite_tour_zero_par_periode` | 7 | Prévu |

## Livrables

| ID | Livrable | Objectifs | Emplacement | Phase | Statut |
| --- | --- | --- | --- | --- | --- |
| L1 | Spécifications fonctionnelles et techniques | Tous | `docs/L1_specifications.md` | 1 | v1.1 relue (reviewer-tester, financial-critic), en attente de validation |
| L2 | Prototype d'agents | O1, O4 | `src/amundi_agentic/{llm,tools,agents,debate}`, `schemas.py`, `agent_prompts/` | 3 | À faire |
| L3 | Module de construction de portefeuille | O2, O3 | `src/amundi_agentic/{portfolio,rebalancing}` | 4, 5 | À faire |
| L4 | Rapport de performance (backtest et live test) | O5 | `docs/L4_rapport_performance.md`, `runs/` | 7 | À faire |
| L5 | Documentation technique et guide gérant | O4 | `README.md`, `docs/` | 8 | À faire |
| L6 | Plan de déploiement (ALTO) | Tous | `docs/L6_plan_deploiement.md` | 9 | À faire |

## Contraintes transverses du prompt maître

| ID | Contrainte | Exigences L1 | Composants | Tests prévus | Phase | Statut |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | LLM agnostique : interface unique, fournisseur changé par configuration | EX-NF-05, EX-NF-09, EX-NF-14 | `llm/`, `config/llm.yaml` | `test_dependances_entre_modules` (aucun SDK fournisseur hors `llm/`) ; `test_changement_de_fournisseur_par_config_seule` ; `test_juges_rag_passent_par_llmclient` ; sorties validées par Pydantic | 3 | Prévu |
| C2 | Budget 0 € : Gemini, Ollama, Groq, relais sur 429 (mode interactif), cache, journal des quotas, budget d'appels | EX-NF-01 à EX-NF-04, EX-NF-08, EX-NF-13, EX-NF-14 | `llm/`, `evaluation/budget.py` | `test_relais_sur_429_simulee_en_mode_interactif` ; `test_mode_evaluation_sans_relais_pause_sur_429` ; `test_requete_identique_servie_par_le_cache` ; `test_alerte_a_80_pourcent_du_quota` ; `test_estimation_budget_formule` ; `test_backtest_refuse_si_budget_depasse` | 3, 7 | Prévu |
| C3 | Données gratuites, licences documentées | EX-O2-10 | `data/` | Rapport de couverture par source | 2 | Prévu |
| C4 | Données point-in-time | EX-NF-11, EX-O1-16, EX-O1-14 | `data/pit.py` (`as_of(date)`) | `test_aucune_donnee_posterieure_a_t` (prix, macro avec millésimes, dépôts, XBRL, news, ESG, change) ; `test_fuseau_edgar_converti` | 2 | Prévu |
| C5 | ESG : exclusions avant recommandation, scores, contraintes | EX-O1-10, EX-O2-05, EX-O2-09 | `agents/esg.py`, `data/connectors/esg.py`, `portfolio/` | `test_titre_exclu_jamais_debattu_ni_recommande` ; `test_contrainte_score_esg_minimal` ; `test_couverture_esg_calculee_et_publiee` | 2, 3, 4 | Prévu |
| C6 | Chiffres calculés par des outils, jamais par le LLM | EX-O1-04, EX-O1-05, EX-O4-07 | `tools/`, `portfolio/views.py` | Tests unitaires de chaque outil ; `test_valuation_appelle_ses_outils` | 3 | Prévu |
| C7 | Reproductibilité : graines, versions de modèles et de prompts enregistrées | EX-NF-04, EX-NF-10, EX-NF-13, EX-O5-12 | `llm/records.py`, `debate/`, `evaluation/preregistration.py`, `runs/` | `test_execution_enregistre_modele_servi_prompt_et_graine` ; `test_rejeu_depuis_le_cache_identique` ; `test_modele_servi_constant_sur_un_run` | 3, 7 | Prévu |
| C8 | La suite de tests passe sans clé d'API | EX-NF-12 | `tests/`, CI | LLM simulé (mock) ; tests `llm` et `network` exclus de la CI | 0, 3 | En place (CI) |
| C9 | Avertissement « prototype académique » | EX-O4-04, EX-O4-08 | `README.md`, `app/`, rapports | `test_readme_porte_l_avertissement` ; `test_interface_porte_l_avertissement` ; `test_rapports_portent_l_avertissement` | 0, 6, 7 | Partiel (README) |
| C10 | Secrets uniquement dans `.env`, jamais commités ni journalisés | EX-NF-07 | `.gitignore`, `.env.example`, `llm/` | `test_env_ignore_par_git`, `test_env_example_sans_secret_ni_cle_anthropic`, `test_aucune_cle_dans_les_journaux` | 0, 3 | En place (partiel) |
| C11 | Contrôle du look-ahead bias du LLM | EX-O5-06, EX-O5-07, EX-O5-11 à EX-O5-13, EX-NF-13 | `evaluation/lookahead.py`, `evaluation/live.py`, `evaluation/preregistration.py` | `test_resultats_anterieurs_a_la_fin_entrainement_etiquetes_contamines` ; `test_anonymisation_masque_noms_et_dates` ; `test_evaluation_refusee_sans_preregistrement` | 7 | Prévu |

## Exigences non fonctionnelles sans contrainte C dédiée

| ID | Exigence | Composants | Tests prévus | Phase | Statut |
| --- | --- | --- | --- | --- | --- |
| EX-NF-06 | Latence (analyse d'une date, tableau de bord) | `debate/`, `app/` | Mesure journalisée par run (`duree_s`) | 3, 6 | Prévu |
