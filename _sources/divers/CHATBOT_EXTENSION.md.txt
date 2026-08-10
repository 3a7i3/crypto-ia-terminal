# 🤖 Extension Chatbot Externe (démo)

## Objectif
Permettre à l’utilisateur d’interagir avec un assistant GPT (OpenAI, Azure, HuggingFace, etc.) directement depuis le dashboard ou une interface web.

## Exemple d’intégration (pseudo-code)
```python
import openai
import streamlit as st

def ask_gpt(question, api_key):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message['content']

st.text_input('Posez votre question à l’assistant :', key='user_q')
if st.session_state.get('user_q'):
    answer = ask_gpt(st.session_state['user_q'], api_key=st.secrets['OPENAI_API_KEY'])
    st.write(answer)
```

## Conseils
- Stocker la clé API dans `.streamlit/secrets.toml`
- Limiter le nombre de requêtes pour éviter les surcoûts
- Adapter le prompt pour un contexte trading/évolution

## Pour aller plus loin
- Intégration Slack, Teams, Discord, webapp
- Historique de conversation, upload de fichiers, etc.

---
