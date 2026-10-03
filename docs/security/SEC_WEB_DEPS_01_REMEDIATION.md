# SEC-WEB-DEPS-01 — Remédiation gouvernée des dépendances frontend

Issue : #257
Pull Request : #344
Date : 2026-10-03
Statut : source en certification, aucun déploiement VPS

## 1. Objet

Cette mission corrige la dette de sécurité npm de l'Operator App sans modifier
les autorités scientifiques, financières ou de trading.

La mission ne touche pas :

- PPL ;
- FIN ;
- epoch/configuration de burn-in ;
- stratégie, signal, risque ou sizing ;
- exchange, TESTNET ou LIVE ;
- Advisor runtime ;
- services VPS.

#286 reste applicable pendant toute la mission.

## 2. Baseline de sécurité

Audit capturé pendant APP-UNIFY U8 avant remédiation :

- dépendances auditées : 246 ;
- vulnérabilités totales : 14 ;
- low : 2 ;
- moderate : 4 ;
- high : 7 ;
- critical : 1.

La vulnérabilité critique concernait Vitest. Une dépendance client directe,
`react-router-dom@6.30.1`, était également signalée HIGH via React Router.

Aucun `npm audit fix --force` n'a été utilisé.

## 3. Mise à niveau retenue

### Runtime client

- `react-router-dom` : `6.30.1` → `7.18.4`.

L'application utilise le mode déclaratif : `BrowserRouter`, `Routes`,
`Route`, `Navigate`, `Link`, `NavLink`, `Outlet`,
`useLocation` et `useOutletContext`.

L'adaptation source requise a été limitée à la suppression des anciens flags
`future` v7 déjà devenus le comportement par défaut de React Router 7.

### Chaîne build/test

- `vite` : `5.4.21` → `8.3.2` ;
- `vitest` : `2.1.9` → `4.1.11` ;
- `@vitejs/plugin-react` : `4.7.0` → `6.1.1` ;
- `postcss` : `8.5.14` → `8.5.28`.

Les autres dépendances directes ont été épinglées sur les versions déjà
résolues par le lockfile précédent afin d'éviter une mise à niveau latérale
non gouvernée.

## 4. Génération du lockfile

Le lockfile n'a pas été édité manuellement.

La reconstruction a été exécutée par GitHub Actions depuis un manifeste
entièrement épinglé.

Deux comportements ont été refusés explicitement :

- `--force` ;
- `--legacy-peer-deps`.

Le npm fourni initialement par le runner, `10.9.9`, a rencontré une erreur
interne `Cannot read properties of null (reading 'edgesOut')` pendant une
reconstruction depuis zéro. La reconstruction a alors été rejouée avec
`npm@12.1.0`, sans assouplir les règles de résolution.

Résultat accepté :

- commit du lockfile : `fe71197aafd1c80afa9692e7384ac74f604b28e8` ;
- SHA-256 du lockfile candidat : `eb92e11c58bcce63823631b89056371044d714d742637ecf2123b323a81a4576` ;
- audit candidat : **0 vulnérabilité** ;
- dépendances auditées : 240.

Versions observées dans le lockfile accepté :

- `react-router-dom 7.18.4` ;
- `react-router 7.18.4` ;
- `@vitejs/plugin-react 6.1.1` ;
- `postcss 8.5.28` ;
- `vite 8.3.2` ;
- `vitest 4.1.11` ;
- `@vitest/mocker 4.1.11` ;
- `browserslist 4.29.3` ;
- `nanoid 3.3.19`.

## 5. Première preuve de non-régression

Sur le HEAD contenant le lockfile accepté, Frontend CI a validé :

- installation déterministe ;
- tests frontend ;
- contrats runtime frontend ;
- build de production ;
- hygiène du diff.

Les gates transversales du dépôt restent nécessaires sur le HEAD final avant
merge.

## 6. Critère de clôture

#257 peut recevoir le verdict :

`SEC_WEB_DEPS_01_REMEDIATED`

uniquement lorsque le HEAD final de #344 satisfait :

1. audit npm à zéro sur le lockfile final ;
2. Frontend CI ;
3. Cross-Stack Compatibility Gate ;
4. CI de régression du dépôt ;
5. preuves visuelles APP-UNIFY/WEB affectées ;
6. absence de modification d'autorité scientifique/trading ;
7. merge gouverné dans `main`.

Aucun verdict de cette mission n'autorise un déploiement VPS.
