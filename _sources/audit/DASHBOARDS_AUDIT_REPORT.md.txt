# Rapport d'audit des Dashboards/Applications

Dernière génération : 2026-03-21 16:27

| Fichier | Framework | Script de lancement | Port | Exclu des tests | Documenté | Description |
|---------|-----------|---------------------|------|-----------------|------------|-------------|
| evolution_3d_view.py | Streamlit | launch_evolution_3d_view.bat | 8501 | ✅ | ✅ | noqa: F401 |
| evolution_dashboard.py | Streamlit | launch_evolution_dashboard.bat | 8501 | ✅ | ✅ |  |
| ONBOARDING_SCRIPT.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| ai_autonomous_loop\feedback_dashboard.py | Streamlit | launch_feedback_dashboard.bat | 8501 | ✅ | ✅ | Historique rapide |
| crypto_quant_v16\run_autonomous_system.py | Panel |  | 5010 | ❌ | ✅ | Historique pour affichage graphique |
| dashboard\alert_dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 | ✅ | ✅ |  |
| quant-hedge-bot\professional_dashboard.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| results\dashboard_evolution_results.py | Panel |  | 5010 | ❌ | ✅ | Tabs for each world |
| results\dashboard_panel.py | Panel |  | 5010 | ❌ | ✅ | Tabs for each world |
| results\equity_curve_streamlit.py | Streamlit | launch_equity_curve_streamlit.bat | 8501 | ✅ | ✅ | Charger le dernier CSV d'equity curves |
| scripts\crypto_market_scanner.py | Panel |  | 5010 | ❌ | ✅ | cryptos à scanner |
| scripts\crypto_terminal.py | Panel |  | 5010 | ❌ | ✅ | connexion Binance |
| scripts\generate_audit_report.py | Streamlit |  | 8501 | ✅ | ❌ | (.*?) |
| scripts\generate_dashboards_table.py | Streamlit |  | 8501 | ❌ | ✅ | (.*?) |
| scripts\test_panel.py | Panel |  | 5010 | ❌ | ✅ | Créer un dossier dans data/ |
| scripts\test_python.py | Panel |  | 5010 | ❌ | ✅ | Créer un dossier dans data/ |
| supervision\botdoctor_dashboard.py | Streamlit | launch_botdoctor_dashboard.bat | 8501 | ✅ | ✅ | Chargement des données |
| supervision\dashboard_advanced.py | Streamlit | launch_dashboard_advanced.bat | 8501 | ✅ | ✅ | Chargement des données |
| tests\test_alert_dashboard_functional.py | Dash |  | 8050 | ❌ | ✅ | Teste le filtrage par module dans le dashboard. |
| quant_hedge_ai\dashboard\quant_terminal_v12.py | Panel | launch_quant_terminal_v12.bat | 5010 | ✅ | ✅ |  |
| quant-trading-system\dashboard\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 | ❌ | ✅ |  |
| quant-trading-system\dashboard\dash_app.py | Dash | launch_dash_app.bat | 8050 | ✅ | ✅ |  |
| quant-trading-system\dashboard\panel_overview.py | Panel | launch_panel_overview.bat | 5010 | ✅ | ✅ |  |
| quant-hedge-bot\dashboard\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 | ❌ | ✅ |  |
| quant-bot-v3-pro\dashboard\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 | ❌ | ✅ | Add parent to path |
| quant-ai-system\dashboard\streamlit_dashboard.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| my_trading_system\ui\dashboard_my_trading_panel.py | Panel |  | 5010 | ❌ | ✅ |  |
| my_trading_system\ui\dashboard_panel.py | Panel |  | 5010 | ❌ | ✅ |  |
| my_trading_system\ui\panel_test_minimal.py | Panel |  | 5010 | ❌ | ✅ | Hello Panel!\nSi tu vois ce message, Panel fonctionne.").servable() |
| crypto_quant_v16\supervision\dashboard_web.py | Streamlit |  | 8501 | ❌ | ✅ | Exécution autonome pour test rapide |
| crypto_quant_v16\tests\test_quant_dashboard.py | Panel |  | 5010 | ❌ | ✅ | Should instantiate dashboard main objects |
| crypto_quant_v16\tests\test_quant_dashboard_v16.py | Panel |  | 5010 | ❌ | ✅ | header, controls, tabs |
| crypto_quant_v16\tests\test_quant_dashboard_v26.py | Panel |  | 5010 | ❌ | ✅ | Should instantiate without error |
| crypto_quant_v16\tests\test_quant_dashboard_v26_visual.py | Panel |  | 5010 | ❌ | ✅ | Configure headless Chrome |
| crypto_quant_v16\tests\test_quant_dashboard_v26_widgets.py | Panel |  | 5010 | ❌ | ✅ | Test symbol select widget exists and can be set |
| crypto_quant_v16\ui\components.py | Panel |  | 5010 | ❌ | ✅ | Panel widget pour choisir dynamiquement les indicateurs à afficher sur le graphique principal. |
| crypto_quant_v16\ui\quant_dashboard.py | Panel | launch_quant_dashboard_v16.bat | 5010 | ✅ | ✅ |  |
| crypto_quant_v16\ui\quant_dashboard_v13.py | Panel |  | 5010 | ❌ | ✅ | Cluster Status panel |
| crypto_quant_v16\ui\quant_dashboard_v26.py | Panel |  | 5010 | ❌ | ✅ |  |
| bot-v3\interface\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 | ❌ | ✅ | Add parent directory to path |
| .venv\Lib\site-packages\ipykernel_launcher.py | Jupyter |  | 8888 | ❌ | ❌ | Entry point for launching an IPython kernel. |
| .venv\Lib\site-packages\ipython_pygments_lexers.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\altair\_magics.py | Jupyter |  | 8888 | ❌ | ❌ | Magic functions for rendering vega-lite specifications. |
| .venv\Lib\site-packages\annotated_text\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Writes text with annotations into your Streamlit app. |
| .venv\Lib\site-packages\camera_input_live\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\comm\base_comm.py | Jupyter |  | 8888 | ❌ | ❌ | Default classes for Comm and CommManager, for usage in IPython. |
| .venv\Lib\site-packages\comm\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Comm package. |
| .venv\Lib\site-packages\dotenv\ipython.py | Jupyter |  | 8888 | ❌ | ❌ | Register the %dotenv magic. |
| .venv\Lib\site-packages\dotenv\main.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\executing\executing.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\fastapi\utils.py | FastAPI |  | 8080 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\pyodide.py | Panel |  | 5010 | ❌ | ✅ | Used to render elements to an image format (svg or png) if requested |
| .venv\Lib\site-packages\hvplot\fugue.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\hvplot\interactive.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\hvplot\ui.py | Panel | launch_equity_curve_streamlit.bat | 5010 | ❌ | ✅ | Explore your data and design your plot via an interactive user interface. |
| .venv\Lib\site-packages\hvplot\util.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\hvplot\utilities.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\hvplot\__init__.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\ipykernel\compiler.py | Jupyter |  | 8888 | ❌ | ❌ | Compiler helpers for the debugger. |
| .venv\Lib\site-packages\ipykernel\connect.py | Jupyter |  | 8888 | ❌ | ❌ | Connection file-related utilities for the kernel |
| .venv\Lib\site-packages\ipykernel\debugger.py | Jupyter |  | 8888 | ❌ | ❌ | Debugger implementation for the IPython kernel. |
| .venv\Lib\site-packages\ipykernel\displayhook.py | Jupyter |  | 8888 | ❌ | ❌ | Replacements for sys.displayhook that publish over ZMQ. |
| .venv\Lib\site-packages\ipykernel\embed.py | Jupyter |  | 8888 | ❌ | ❌ | Simple function for embedding an IPython kernel |
| .venv\Lib\site-packages\ipykernel\eventloops.py | Jupyter |  | 8888 | ❌ | ❌ | Event loop integration for the ZeroMQ-based kernels. |
| .venv\Lib\site-packages\ipykernel\heartbeat.py | Jupyter |  | 8888 | ❌ | ❌ | The client and server for a basic ping-pong style heartbeat. |
| .venv\Lib\site-packages\ipykernel\iostream.py | Jupyter |  | 8888 | ❌ | ❌ | Wrappers for forwarding stdout/stderr over zmq |
| .venv\Lib\site-packages\ipykernel\ipkernel.py | Jupyter |  | 8888 | ❌ | ❌ | The IPython kernel implementation |
| .venv\Lib\site-packages\ipykernel\jsonutil.py | Jupyter |  | 8888 | ❌ | ❌ | Utilities to manipulate JSON objects. |
| .venv\Lib\site-packages\ipykernel\kernelapp.py | Jupyter |  | 8888 | ❌ | ❌ | An Application for launching a kernel |
| .venv\Lib\site-packages\ipykernel\kernelbase.py | Jupyter |  | 8888 | ❌ | ❌ | Base class for a kernel that talks to frontends over 0MQ. |
| .venv\Lib\site-packages\ipykernel\kernelspec.py | Jupyter |  | 8888 | ❌ | ❌ | The IPython kernel spec for Jupyter |
| .venv\Lib\site-packages\ipykernel\parentpoller.py | Jupyter |  | 8888 | ❌ | ❌ | A parent poller for unix. |
| .venv\Lib\site-packages\ipykernel\zmqshell.py | Jupyter |  | 8888 | ❌ | ❌ | A ZMQ-based subclass of InteractiveShell. |
| .venv\Lib\site-packages\ipykernel\_eventloop_macos.py | Jupyter |  | 8888 | ❌ | ❌ | Eventloop hook for OS X |
| .venv\Lib\site-packages\IPython\display.py | Jupyter |  | 8888 | ❌ | ❌ | Public API for display tools in IPython. |
| .venv\Lib\site-packages\IPython\paths.py | Jupyter |  | 8888 | ❌ | ❌ | Find files and directories which IPython uses. |
| .venv\Lib\site-packages\IPython\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\__main__.py | Jupyter |  | 8888 | ❌ | ❌ | Terminal-based IPython entry point. |
| .venv\Lib\site-packages\ipywidgets\comm.py | Jupyter |  | 8888 | ❌ | ❌ | compatibility shim for ipykernel < 6.18 |
| .venv\Lib\site-packages\ipywidgets\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Interactive widgets for the Jupyter notebook. |
| .venv\Lib\site-packages\jedi\settings.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\jedi\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\joblib\func_inspect.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\joblib\hashing.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\joblib\memory.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\jupyter_client\adapter.py | Jupyter |  | 8888 | ❌ | ❌ | Adapters for Jupyter msg spec versions. |
| .venv\Lib\site-packages\jupyter_client\client.py | Jupyter |  | 8888 | ❌ | ❌ | Base class to manage the interaction with a running kernel |
| .venv\Lib\site-packages\jupyter_client\consoleapp.py | Jupyter |  | 8888 | ❌ | ❌ | A minimal application base mixin for all ZMQ based IPython frontends. |
| .venv\Lib\site-packages\jupyter_client\kernelspec.py | Jupyter |  | 8888 | ❌ | ❌ | Tools for managing kernel specs |
| .venv\Lib\site-packages\jupyter_client\kernelspecapp.py | Jupyter |  | 8888 | ❌ | ❌ | Apps for managing kernel specs. |
| .venv\Lib\site-packages\jupyter_client\session.py | Jupyter |  | 8888 | ❌ | ❌ | Session object for building, serializing, sending, and receiving messages. |
| .venv\Lib\site-packages\jupyter_client\win_interrupt.py | Jupyter |  | 8888 | ❌ | ❌ | Use a Windows event to interrupt a child process like SIGINT. |
| .venv\Lib\site-packages\jupyter_console\app.py | Jupyter | launch_dash_app.bat | 8888 | ❌ | ❌ | A minimal application using the ZMQ-based terminal IPython frontend. |
| .venv\Lib\site-packages\jupyter_console\completer.py | Jupyter |  | 8888 | ❌ | ❌ | Adapt readline completer interface to make ZMQ request. |
| .venv\Lib\site-packages\jupyter_console\ptshell.py | Jupyter |  | 8888 | ❌ | ❌ | IPython terminal interface using prompt_toolkit in place of readline |
| .venv\Lib\site-packages\jupyter_console\zmqhistory.py | Jupyter |  | 8888 | ❌ | ❌ | ZMQ Kernel History accessor and manager. |
| .venv\Lib\site-packages\jupyter_core\application.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\jupyter_core\command.py | Jupyter |  | 8888 | ❌ | ❌ | The root `jupyter` command. |
| .venv\Lib\site-packages\jupyter_core\migrate.py | Jupyter |  | 8888 | ❌ | ❌ | Migrating IPython < 4.0 to Jupyter |
| .venv\Lib\site-packages\jupyter_core\paths.py | Jupyter |  | 8888 | ❌ | ❌ | Path utility functions. |
| .venv\Lib\site-packages\jupyter_core\troubleshoot.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\jupyter_server\serverapp.py | Jupyter |  | 8888 | ❌ | ❌ | A tornado based Jupyter server. |
| .venv\Lib\site-packages\jupyter_server\utils.py | Jupyter |  | 8888 | ❌ | ❌ | Notebook related utilities |
| .venv\Lib\site-packages\markdownlit\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Apply custom CSS in a Streamlit app. |
| .venv\Lib\site-packages\matplotlib\animation.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\backend_bases.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\figure.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\pyplot.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\rcsetup.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\text.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib_inline\backend_inline.py | Jupyter |  | 8888 | ❌ | ❌ | A matplotlib backend for publishing figures via display_data |
| .venv\Lib\site-packages\matplotlib_inline\config.py | Jupyter |  | 8888 | ❌ | ❌ | Configurable for configuring the IPython inline backend |
| .venv\Lib\site-packages\matplotlib_inline\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | noqa |
| .venv\Lib\site-packages\nbclient\client.py | Jupyter |  | 8888 | ❌ | ❌ | nbclient implementation. |
| .venv\Lib\site-packages\nbclient\jsonutil.py | Jupyter |  | 8888 | ❌ | ❌ | Utilities to manipulate JSON objects. |
| .venv\Lib\site-packages\nbconvert\nbconvertapp.py | Jupyter |  | 8888 | ❌ | ❌ | NbConvert is a utility for conversion of .ipynb files. |
| .venv\Lib\site-packages\nbformat\converter.py | Jupyter |  | 8888 | ❌ | ❌ | API for converting notebooks between versions. |
| .venv\Lib\site-packages\nbformat\current.py | Jupyter |  | 8888 | ❌ | ❌ | Deprecated API for working with notebooks |
| .venv\Lib\site-packages\nbformat\reader.py | Jupyter |  | 8888 | ❌ | ❌ | API for reading notebooks of different versions |
| .venv\Lib\site-packages\nbformat\sentinel.py | Jupyter |  | 8888 | ❌ | ❌ | Sentinel class for constants with useful reprs |
| .venv\Lib\site-packages\nbformat\sign.py | Jupyter |  | 8888 | ❌ | ❌ | Utilities for signing notebooks |
| .venv\Lib\site-packages\nbformat\validator.py | Jupyter |  | 8888 | ❌ | ❌ | Notebook format validators. |
| .venv\Lib\site-packages\nbformat\_imports.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\nbformat\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | The Jupyter notebook format |
| .venv\Lib\site-packages\notebook_shim\traits.py | Jupyter |  | 8888 | ❌ | ❌ | Whether to enable MathJax for typesetting math/TeX |
| .venv\Lib\site-packages\numpy\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\conftest.py | Jupyter |  | 8888 | ✅ | ❌ |  |
| .venv\Lib\site-packages\panel\config.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\custom.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\interact.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\panel\param.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\reactive.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\viewable.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\__init__.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\param\ipython.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\PIL\Image.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\PIL\ImageShow.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\playhouse\flask_utils.py | Flask |  | 5000 | ❌ | ❌ |  |
| .venv\Lib\site-packages\plotly\tools.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\prompt_toolkit\cursor_shapes.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\prompt_toolkit\renderer.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pyviz_comms\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\seaborn\palettes.py | Jupyter |  | 8888 | ❌ | ❌ | Set the color palette in a with statement, otherwise be a list. |
| .venv\Lib\site-packages\seaborn\widgets.py | Jupyter |  | 8888 | ❌ | ❌ | Create a matplotlib colormap that will be updated by the widgets. |
| .venv\Lib\site-packages\streamlit\config.py | Streamlit |  | 8501 | ❌ | ✅ | Loads the configuration data. |
| .venv\Lib\site-packages\streamlit\delta_generator.py | Streamlit |  | 8501 | ❌ | ✅ | Allows us to create and absorb changes (aka Deltas) to elements. |
| .venv\Lib\site-packages\streamlit\deprecation_util.py | Streamlit |  | 8501 | ❌ | ✅ | True if we should print deprecation warnings to the browser. |
| .venv\Lib\site-packages\streamlit\error_util.py | Streamlit |  | 8501 | ❌ | ✅ | Show the exception on the frontend. |
| .venv\Lib\site-packages\streamlit\user_info.py | Streamlit |  | 8501 | ❌ | ✅ | Initiate the login flow for the given provider. |
| .venv\Lib\site-packages\streamlit\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Streamlit. |
| .venv\Lib\site-packages\streamlit_avatar\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_card\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Creates a UI card like component. |
| .venv\Lib\site-packages\streamlit_embedcode\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Strip trailing slash if present on link. |
| .venv\Lib\site-packages\streamlit_faker\chart.py | Streamlit |  | 8501 | ❌ | ✅ | Collects a CSV/JSON file from a URL and load it into a dataframe, with appropriate caching (memo) |
| .venv\Lib\site-packages\streamlit_faker\data_display.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_faker\input.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_faker\media.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_faker\status.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_faker\text.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_image_coordinates\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_theme\example.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_theme\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Show the installed version of the Streamlit Theme package. |
| .venv\Lib\site-packages\streamlit_toggle\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | D3D3D3', active_color=" |
| .venv\Lib\site-packages\streamlit_vertical_slider\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | E5E9F1", |
| .venv\Lib\site-packages\st_keyup\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\tqdm\autonotebook.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\tqdm\notebook.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\traitlets\log.py | Jupyter |  | 8888 | ❌ | ❌ | Grab the global logger instance. |
| .venv\Lib\site-packages\traitlets\traitlets.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\widgetsnbextension\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Interactive widgets for the Jupyter notebook. |
| .venv\Lib\site-packages\xgboost\plotting.py | Jupyter |  | 8888 | ❌ | ❌ | Plotting Library. |
| .venv\Lib\site-packages\_pytest\debugging.py | Jupyter |  | 8888 | ❌ | ❌ | Interactive debugging with PDB, the Python Debugger. |
| .venv\Lib\site-packages\zmq\ssh\forward.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\zmq\ssh\tunnel.py | Jupyter |  | 8888 | ❌ | ❌ | Basic ssh tunnel utilities, and convenience functions for tunneling |
| .venv\Lib\site-packages\traitlets\config\application.py | Jupyter |  | 8888 | ❌ | ❌ | A base class for a configurable application. |
| .venv\Lib\site-packages\traitlets\config\argcomplete_config.py | Jupyter |  | 8888 | ❌ | ❌ | Helper utilities for integrating argcomplete with traitlets |
| .venv\Lib\site-packages\traitlets\config\configurable.py | Jupyter |  | 8888 | ❌ | ❌ | A base class for objects that are configurable. |
| .venv\Lib\site-packages\traitlets\config\loader.py | Jupyter |  | 8888 | ❌ | ❌ | A simple configuration system. |
| .venv\Lib\site-packages\traitlets\config\manager.py | Jupyter |  | 8888 | ❌ | ❌ | Manager to read and modify config data in JSON files. |
| .venv\Lib\site-packages\traitlets\config\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Copyright (c) IPython Development Team. |
| .venv\Lib\site-packages\traitlets\utils\importstring.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\traitlets\utils\nested_update.py | Jupyter |  | 8888 | ❌ | ❌ | Merge two nested dictionaries. |
| .venv\Lib\site-packages\traitlets\utils\sentinel.py | Jupyter |  | 8888 | ❌ | ❌ | Sentinel class for constants with useful reprs |
| .venv\Lib\site-packages\traitlets\utils\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Find a file by looking through a sequence of paths. |
| .venv\Lib\site-packages\streamlit_extras\add_vertical_space\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\altex\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Collects a CSV/JSON file from a URL and load it into a dataframe, with appropriate caching (memo) |
| .venv\Lib\site-packages\streamlit_extras\app_logo\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Add a logo (from logo_url) on the top of the navigation page of a multipage app. |
| .venv\Lib\site-packages\streamlit_extras\badges\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Easily create a visual badge for PyPI, GitHub, Streamlit Cloud or other social platforms. |
| .venv\Lib\site-packages\streamlit_extras\bottom_container\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\button_selector\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\buy_me_a_coffee\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\camera_input_live\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | See a new image every second") |
| .venv\Lib\site-packages\streamlit_extras\capture\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Redirect STDOUT and STDERR to streamlit functions. |
| .venv\Lib\site-packages\streamlit_extras\chart_annotations\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\chart_container\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Embed chart in a (chart, data, export, explore) tabs container to let the viewer explore and export its underlying data. |
| .venv\Lib\site-packages\streamlit_extras\colored_header\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Add colorful headers to your Streamlit app. |
| .venv\Lib\site-packages\streamlit_extras\concurrency_limiter\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Add concurrency_limiter decorator to your Streamlit app. |
| .venv\Lib\site-packages\streamlit_extras\customize_running\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\dataframe_explorer\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\echo_expander\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\floating_button\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\function_explorer\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Gives a Streamlit UI to any function. |
| .venv\Lib\site-packages\streamlit_extras\great_tables\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\grid\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\image_coordinates\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\image_in_tables\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\image_selector\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\keyboard_text\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | <style> |
| .venv\Lib\site-packages\streamlit_extras\keyboard_url\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\let_it_rain\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\mandatory_date_range\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\markdownlit\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | mdlit("{code}") |
| .venv\Lib\site-packages\streamlit_extras\mention\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\metric_cards\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\no_default_selectbox\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\pdf_viewer\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Display a PDF document. |
| .venv\Lib\site-packages\streamlit_extras\prometheus\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Custom OpenMetrics collected via protobuf is not currently supported. |
| .venv\Lib\site-packages\streamlit_extras\row\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\sandbox\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\skeleton\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\star_rating\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\stateful_button\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\stateful_chat\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\stodo\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Create a to_do item |
| .venv\Lib\site-packages\streamlit_extras\stoggle\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\streaming_write\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Drop-in replacement for `st.write` with streaming support. |
| .venv\Lib\site-packages\streamlit_extras\stylable_container\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\st_keyup\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\switch_page_button\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\tags\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\theme\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\toggle_switch\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | On/Off Toggle Switch with color customizations. |
| .venv\Lib\site-packages\streamlit_extras\vertical_slider\__init__.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\word_importances\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Adds a background color to each word based on its importance (float from -1 to 1) |
| .venv\Lib\site-packages\streamlit_extras\prometheus\example\app.py | Streamlit | launch_dash_app.bat | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit_extras\prometheus\example\metrics.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\commands\echo.py | Streamlit |  | 8501 | ❌ | ✅ | Use in a `with` block to draw some code on the app, then execute it. |
| .venv\Lib\site-packages\streamlit\commands\execution_control.py | Streamlit |  | 8501 | ❌ | ✅ | Stops execution immediately. |
| .venv\Lib\site-packages\streamlit\commands\logo.py | Streamlit |  | 8501 | ❌ | ✅ | Handle App logos. |
| .venv\Lib\site-packages\streamlit\commands\navigation.py | Streamlit |  | 8501 | ❌ | ✅ | Convert various input types to StreamlitPage objects. |
| .venv\Lib\site-packages\streamlit\commands\page_config.py | Streamlit |  | 8501 | ❌ | ✅ | Return the string to pass to the frontend to have it show |
| .venv\Lib\site-packages\streamlit\connections\base_connection.py | Streamlit |  | 8501 | ❌ | ✅ | The abstract base class that all Streamlit Connections must inherit from. |
| .venv\Lib\site-packages\streamlit\connections\snowflake_connection.py | Streamlit |  | 8501 | ❌ | ✅ | Base class for Snowflake connections. |
| .venv\Lib\site-packages\streamlit\connections\snowpark_connection.py | Streamlit |  | 8501 | ❌ | ✅ | A connection to Snowpark using snowflake.snowpark.session.Session. Initialize using |
| .venv\Lib\site-packages\streamlit\connections\sql_connection.py | Streamlit |  | 8501 | ❌ | ✅ | A connection to a SQL database using a SQLAlchemy Engine. |
| .venv\Lib\site-packages\streamlit\elements\alert.py | Streamlit | launch_alert_dashboard.bat | 8501 | ❌ | ✅ | Display error message. |
| .venv\Lib\site-packages\streamlit\elements\arrow.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\elements\balloons.py | Streamlit |  | 8501 | ❌ | ✅ | Draw celebratory balloons. |
| .venv\Lib\site-packages\streamlit\elements\code.py | Streamlit |  | 8501 | ❌ | ✅ | Display a code block with optional syntax highlighting. |
| .venv\Lib\site-packages\streamlit\elements\deck_gl_json_chart.py | Streamlit |  | 8501 | ❌ | ✅ | Parse and check the user provided selection modes. |
| .venv\Lib\site-packages\streamlit\elements\dialog_decorator.py | Streamlit |  | 8501 | ❌ | ✅ | Check the current stack for existing DeltaGenerator's of type 'dialog'. |
| .venv\Lib\site-packages\streamlit\elements\empty.py | Streamlit |  | 8501 | ❌ | ✅ | Insert a single-element container. |
| .venv\Lib\site-packages\streamlit\elements\exception.py | Streamlit |  | 8501 | ❌ | ✅ | Display an exception. |
| .venv\Lib\site-packages\streamlit\elements\form.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\elements\graphviz_chart.py | Streamlit |  | 8501 | ❌ | ✅ | Streamlit support for GraphViz charts. |
| .venv\Lib\site-packages\streamlit\elements\heading.py | Streamlit |  | 8501 | ❌ | ✅ | Display text in header formatting. |
| .venv\Lib\site-packages\streamlit\elements\help.py | Streamlit |  | 8501 | ❌ | ✅ | Allows us to create and absorb changes (aka Deltas) to elements. |
| .venv\Lib\site-packages\streamlit\elements\html.py | Streamlit |  | 8501 | ❌ | ✅ | Insert HTML into your app. |
| .venv\Lib\site-packages\streamlit\elements\iframe.py | Streamlit |  | 8501 | ❌ | ✅ | Load a remote URL in an iframe. |
| .venv\Lib\site-packages\streamlit\elements\image.py | Streamlit |  | 8501 | ❌ | ✅ | Image marshalling. |
| .venv\Lib\site-packages\streamlit\elements\json.py | Streamlit |  | 8501 | ❌ | ✅ | A repr function for json.dumps default arg, which tries to serialize sets |
| .venv\Lib\site-packages\streamlit\elements\layouts.py | Streamlit |  | 8501 | ❌ | ✅ | Serializer/deserializer for expander widget state. |
| .venv\Lib\site-packages\streamlit\elements\map.py | Streamlit |  | 8501 | ❌ | ✅ | A wrapper for simple PyDeck scatter charts. |
| .venv\Lib\site-packages\streamlit\elements\markdown.py | Streamlit |  | 8501 | ❌ | ✅ | Display string formatted as Markdown. |
| .venv\Lib\site-packages\streamlit\elements\media.py | Streamlit |  | 8501 | ❌ | ✅ | Display an audio player. |
| .venv\Lib\site-packages\streamlit\elements\metric.py | Streamlit |  | 8501 | ❌ | ✅ | Display a metric in big bold font, with an optional indicator of how the metric changed. |
| .venv\Lib\site-packages\streamlit\elements\pdf.py | Streamlit |  | 8501 | ❌ | ✅ | Get the PDF custom component if available. |
| .venv\Lib\site-packages\streamlit\elements\plotly_chart.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\elements\progress.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\elements\pyplot.py | Streamlit |  | 8501 | ❌ | ✅ | Streamlit support for Matplotlib PyPlot charts. |
| .venv\Lib\site-packages\streamlit\elements\snow.py | Streamlit |  | 8501 | ❌ | ✅ | Draw celebratory snowfall. |
| .venv\Lib\site-packages\streamlit\elements\space.py | Streamlit |  | 8501 | ❌ | ✅ | Add vertical or horizontal space. |
| .venv\Lib\site-packages\streamlit\elements\spinner.py | Streamlit |  | 8501 | ❌ | ✅ | Display a loading spinner while executing a block of code. |
| .venv\Lib\site-packages\streamlit\elements\table.py | Streamlit |  | 8501 | ❌ | ✅ | Parse and check the user provided border mode. |
| .venv\Lib\site-packages\streamlit\elements\text.py | Streamlit |  | 8501 | ❌ | ✅ | Write text without Markdown or HTML parsing. |
| .venv\Lib\site-packages\streamlit\elements\toast.py | Streamlit |  | 8501 | ❌ | ✅ | Display a short message, known as a notification "toast". |
| .venv\Lib\site-packages\streamlit\elements\vega_charts.py | Streamlit |  | 8501 | ❌ | ✅ | Collection of chart commands that are rendered via our vega-lite chart component. |
| .venv\Lib\site-packages\streamlit\elements\write.py | Streamlit |  | 8501 | ❌ | ✅ | Stream a generator, iterable, or stream-like sequence to the app. |
| .venv\Lib\site-packages\streamlit\hello\animation_demo.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\hello\dataframe_demo.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\hello\hello.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\hello\mapping_demo.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\hello\plotting_demo.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\hello\streamlit_app.py | Streamlit |  | 8501 | ❌ | ✅ | Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022-2026) |
| .venv\Lib\site-packages\streamlit\hello\utils.py | Streamlit |  | 8501 | ❌ | ✅ | Showing the code of the demo. |
| .venv\Lib\site-packages\streamlit\navigation\page.py | Streamlit |  | 8501 | ❌ | ✅ | Configure a page for ``st.navigation`` in a multipage app. |
| .venv\Lib\site-packages\streamlit\runtime\app_session.py | Streamlit |  | 8501 | ❌ | ✅ | Randomly generate a unique ID for a script execution. |
| .venv\Lib\site-packages\streamlit\runtime\connection_factory.py | Streamlit |  | 8501 | ❌ | ✅ | Create an instance of connection_class with the given name and kwargs. |
| .venv\Lib\site-packages\streamlit\runtime\context.py | Streamlit |  | 8501 | ❌ | ✅ | Get the ClientContext for the current session. |
| .venv\Lib\site-packages\streamlit\runtime\fragment.py | Streamlit |  | 8501 | ❌ | ✅ | A key-value store for Fragments. Used to implement the @st.fragment decorator. |
| .venv\Lib\site-packages\streamlit\runtime\secrets.py | Streamlit |  | 8501 | ❌ | ✅ | SecretErrorMessages stores all error messages we use for secrets to allow customization |
| .venv\Lib\site-packages\streamlit\web\cli.py | Streamlit |  | 8501 | ❌ | ✅ | A script which is run when the Streamlit package is executed. |
| .venv\Lib\site-packages\streamlit\web\server\app_discovery.py | Streamlit |  | 8501 | ❌ | ✅ | App discovery utilities for detecting ASGI app instances in scripts. |
| .venv\Lib\site-packages\streamlit\web\server\bidi_component_request_handler.py | Streamlit |  | 8501 | ❌ | ✅ | Serve static assets for Custom Components v2. |
| .venv\Lib\site-packages\streamlit\web\server\component_request_handler.py | Streamlit |  | 8501 | ❌ | ✅ | Disable cache for HTML files. |
| .venv\Lib\site-packages\streamlit\web\server\server.py | Streamlit |  | 8501 | ❌ | ✅ | Get the websocket ping interval and timeout from config or defaults. |
| .venv\Lib\site-packages\streamlit\testing\v1\app_test.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\runtime\caching\cached_message_replay.py | Streamlit |  | 8501 | ❌ | ✅ | An element's message and related metadata for |
| .venv\Lib\site-packages\streamlit\runtime\caching\cache_data_api.py | Streamlit |  | 8501 | ❌ | ✅ | @st.cache_data: pickle-based caching. |
| .venv\Lib\site-packages\streamlit\runtime\caching\cache_resource_api.py | Streamlit |  | 8501 | ❌ | ✅ | @st.cache_resource implementation. |
| .venv\Lib\site-packages\streamlit\runtime\caching\cache_utils.py | Streamlit |  | 8501 | ❌ | ✅ | Common cache logic shared by st.cache_data and st.cache_resource. |
| .venv\Lib\site-packages\streamlit\runtime\caching\legacy_cache_api.py | Streamlit |  | 8501 | ❌ | ✅ | A library of caching utilities. |
| .venv\Lib\site-packages\streamlit\runtime\scriptrunner\exec_code.py | Jupyter |  | 8888 | ❌ | ❌ | A context for prepending a directory to sys.path for a second. |
| .venv\Lib\site-packages\streamlit\runtime\scriptrunner\magic.py | Streamlit |  | 8501 | ❌ | ✅ | Modifies the code to support magic Streamlit commands. |
| .venv\Lib\site-packages\streamlit\runtime\scriptrunner\magic_funcs.py | Streamlit |  | 8501 | ❌ | ✅ | The function that gets magic-ified into Streamlit apps. |
| .venv\Lib\site-packages\streamlit\runtime\state\query_params_proxy.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\elements\lib\column_types.py | Streamlit |  | 8501 | ❌ | ✅ | Validate a color for a chart column. |
| .venv\Lib\site-packages\streamlit\elements\lib\mutable_expander_container.py | Streamlit |  | 8501 | ❌ | ✅ | A container returned by ``st.expander``. |
| .venv\Lib\site-packages\streamlit\elements\lib\mutable_popover_container.py | Streamlit |  | 8501 | ❌ | ✅ | A container returned by ``st.popover``. |
| .venv\Lib\site-packages\streamlit\elements\lib\mutable_tab_container.py | Streamlit |  | 8501 | ❌ | ✅ | A container returned for each tab in ``st.tabs``. |
| .venv\Lib\site-packages\streamlit\elements\widgets\audio_input.py | Streamlit |  | 8501 | ❌ | ✅ | Display a widget that returns an audio recording from the user's microphone. |
| .venv\Lib\site-packages\streamlit\elements\widgets\button.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\elements\widgets\button_group.py | Streamlit |  | 8501 | ❌ | ✅ | String-based serde for single-select ButtonGroup widgets. |
| .venv\Lib\site-packages\streamlit\elements\widgets\camera_input.py | Streamlit |  | 8501 | ❌ | ✅ | Display a widget that returns pictures from the user's webcam. |
| .venv\Lib\site-packages\streamlit\elements\widgets\chat.py | Streamlit |  | 8501 | ❌ | ✅ | Represents the value returned by `st.chat_input` after user interaction. |
| .venv\Lib\site-packages\streamlit\elements\widgets\checkbox.py | Streamlit |  | 8501 | ❌ | ✅ | Display a checkbox widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\color_picker.py | Streamlit |  | 8501 | ❌ | ✅ | Normalize a hex color to include the # prefix. |
| .venv\Lib\site-packages\streamlit\elements\widgets\data_editor.py | Streamlit |  | 8501 | ❌ | ✅ |  |
| .venv\Lib\site-packages\streamlit\elements\widgets\feedback.py | Streamlit | launch_feedback_dashboard.bat | 8501 | ❌ | ✅ | Get the number of options for the given feedback type. |
| .venv\Lib\site-packages\streamlit\elements\widgets\file_uploader.py | Streamlit |  | 8501 | ❌ | ✅ | Display a file uploader widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\multiselect.py | Streamlit |  | 8501 | ❌ | ✅ | Initialize the MultiSelectSerde. |
| .venv\Lib\site-packages\streamlit\elements\widgets\number_input.py | Streamlit |  | 8501 | ❌ | ✅ | Display a numeric input widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\radio.py | Streamlit |  | 8501 | ❌ | ✅ | Serializer/deserializer for Radio widget values. |
| .venv\Lib\site-packages\streamlit\elements\widgets\selectbox.py | Streamlit |  | 8501 | ❌ | ✅ | Initialize the SelectboxSerde. |
| .venv\Lib\site-packages\streamlit\elements\widgets\select_slider.py | Streamlit |  | 8501 | ❌ | ✅ | Serializer/deserializer for select_slider widget values. |
| .venv\Lib\site-packages\streamlit\elements\widgets\slider.py | Streamlit |  | 8501 | ❌ | ✅ | Restore times/datetimes to original timezone (dates are always naive). |
| .venv\Lib\site-packages\streamlit\elements\widgets\text_widgets.py | Streamlit |  | 8501 | ❌ | ✅ | Display a single-line text input widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\time_widgets.py | Streamlit |  | 8501 | ❌ | ✅ | Return a time without seconds, microseconds, or timezone info. |
| .venv\Lib\site-packages\streamlit\components\v1\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Contains the files and modules for the exposed API. |
| .venv\Lib\site-packages\streamlit\components\v2\types.py | Streamlit |  | 8501 | ❌ | ✅ | Shared typing utilities for the `st.components.v2` API. |
| .venv\Lib\site-packages\streamlit\components\v2\__init__.py | Streamlit |  | 8501 | ❌ | ✅ | Register the st.components.v2 API namespace. |
| .venv\Lib\site-packages\seaborn\_core\plot.py | Jupyter |  | 8888 | ❌ | ❌ | The classes for specifying and compiling a declarative visualization. |
| .venv\Lib\site-packages\scipy\signal\_signaltools.py | Jupyter |  | 8888 | ❌ | ❌ | Determine if inputs arrays need to be swapped in `"valid"` mode. |
| .venv\Lib\site-packages\pyviz_comms\tests\test_extension.py | Jupyter |  | 8888 | ❌ | ❌ | Store the default values to reset them in the get_ipython fixture |
| .venv\Lib\site-packages\pydeck\io\html.py | Jupyter |  | 8888 | ❌ | ❌ | Serializes Python booleans to JavaScript. Returns non-boolean values unchanged. |
| .venv\Lib\site-packages\prompt_toolkit\application\application.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\prompt_toolkit\input\win32.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\prompt_toolkit\output\win32.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\plotly\io\_base_renderers.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\plotly\io\_renderers.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\plotly\offline\offline.py | Jupyter |  | 8888 | ❌ | ❌ | Plotly Offline |
| .venv\Lib\site-packages\plotly\matplotlylib\mplexporter\tools.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\plotly\matplotlylib\mplexporter\renderers\vega_renderer.py | Jupyter |  | 8888 | ❌ | ❌ | Build the HTML representation for IPython. |
| .venv\Lib\site-packages\pip\_vendor\rich\console.py | Jupyter |  | 8888 | ❌ | ❌ | Size of the terminal. |
| .venv\Lib\site-packages\pip\_vendor\rich\jupyter.py | Jupyter |  | 8888 | ❌ | ❌ | \ |
| .venv\Lib\site-packages\pip\_vendor\rich\live.py | Jupyter |  | 8888 | ❌ | ❌ | A thread that calls refresh() at regular intervals. |
| .venv\Lib\site-packages\pip\_vendor\rich\pretty.py | Jupyter |  | 8888 | ❌ | ❌ | Check if an object was created with attrs module. |
| .venv\Lib\site-packages\pip\_vendor\rich\traceback.py | Jupyter |  | 8888 | ❌ | ❌ | Yield start and end positions per line. |
| .venv\Lib\site-packages\panel\io\application.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\io\handlers.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\io\jupyter_executor.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\panel\io\mime_render.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\panel\io\notebook.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\io\pyodide.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\io\resources.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\io\state.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\panel\io\__init__.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\layout\base.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\layout\flex.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\layout\float.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\layout\grid.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\layout\swipe.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\template\base.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\panel\tests\conftest.py | Panel |  | 5010 | ✅ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\test_depends.py | Panel |  | 5010 | ❌ | ✅ | Emits a Param warning |
| .venv\Lib\site-packages\panel\tests\test_docs.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\test_imports.py | Panel |  | 5010 | ❌ | ✅ | \ |
| .venv\Lib\site-packages\panel\tests\test_models.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\util.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\util\warnings.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\util\__init__.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\widgets\tables.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\command\test_serve.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\io\test_handlers.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\io\test_notebook.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\panel\tests\layout\test_accordion.py | Panel |  | 5010 | ❌ | ✅ | Set up a accordion instance |
| .venv\Lib\site-packages\panel\tests\layout\test_tabs.py | Panel |  | 5010 | ❌ | ✅ | Set up a tabs instance |
| .venv\Lib\site-packages\panel\tests\pane\test_alert.py | Panel |  | 5010 | ❌ | ✅ | In this module we test the functionality of the alerts |
| .venv\Lib\site-packages\panel\tests\pane\test_base.py | Panel |  | 5010 | ✅ | ✅ | Ensures internal code correctly detects |
| .venv\Lib\site-packages\panel\tests\pane\test_holoviews.py | Panel |  | 5010 | ❌ | ✅ | Create pane |
| .venv\Lib\site-packages\panel\tests\pane\test_plot.py | Panel |  | 5010 | ❌ | ✅ | Create pane |
| .venv\Lib\site-packages\panel\tests\pane\test_vega.py | Panel |  | 5010 | ❌ | ✅ | Tests for Vega.export() method. |
| .venv\Lib\site-packages\panel\tests\ui\test_auth.py | Panel |  | 5010 | ❌ | ✅ | Loading password page is slow |
| .venv\Lib\site-packages\panel\tests\ui\test_param.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\widgets\test_debugger.py | Panel |  | 5010 | ❌ | ✅ | This module contains tests of the Debugger |
| .venv\Lib\site-packages\panel\tests\widgets\test_select.py | Panel |  | 5010 | ❌ | ✅ | Instantiate with groups and options |
| .venv\Lib\site-packages\panel\tests\widgets\test_speech_to_text.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\widgets\test_terminal.py | Panel |  | 5010 | ❌ | ✅ | This module contains tests of the Terminal |
| .venv\Lib\site-packages\panel\tests\widgets\test_text_to_speech.py | Panel |  | 5010 | ❌ | ✅ | By Aesop |
| .venv\Lib\site-packages\panel\tests\widgets\test_tqdm.py | Panel |  | 5010 | ✅ | ✅ | Tests of the Tqdm indicator |
| .venv\Lib\site-packages\panel\tests\ui\command\test_serve.py | Panel |  | 5010 | ❌ | ✅ | Timeout to ensure websocket is initialized |
| .venv\Lib\site-packages\panel\tests\ui\io\app.py | Panel | launch_dash_app.bat | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\ui\io\test_convert.py | Panel |  | 5010 | ✅ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\ui\io\test_location.py | Panel |  | 5010 | ❌ | ✅ | Simple app to set url by widgets' values |
| .venv\Lib\site-packages\panel\tests\ui\io\test_reload.py | Panel |  | 5010 | ❌ | ✅ | Write and close (on windows the file handle cannot be reopened for reading otherwise) |
| .venv\Lib\site-packages\panel\tests\ui\io\test_resources.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\tests\ui\widgets\test_input.py | Panel |  | 5010 | ❌ | ✅ | 1st week |
| .venv\Lib\site-packages\panel\tests\ui\widgets\test_sliders.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\panel\pane\vtk\vtk.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\pandas\core\accessor.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\core\base.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\core\config_init.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\core\frame.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\util\_print_versions.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\_config\display.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\tests\frame\test_api.py | Jupyter |  | 8888 | ❌ | ❌ | DataFrame whose columns are identifiers shall have them in __dir__. |
| .venv\Lib\site-packages\pandas\tests\indexes\test_base.py | Jupyter |  | 8888 | ✅ | ❌ | TODO: a bunch of scattered tests check this deprecation is enforced. |
| .venv\Lib\site-packages\pandas\tests\resample\test_resampler_grouper.py | Jupyter |  | 8888 | ❌ | ❌ | \ |
| .venv\Lib\site-packages\pandas\tests\io\formats\test_to_html.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\tests\arrays\categorical\test_warnings.py | Jupyter |  | 8888 | ❌ | ❌ | https://github.com/pandas-dev/pandas/issues/16409 |
| .venv\Lib\site-packages\pandas\plotting\_matplotlib\core.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\io\formats\console.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\io\formats\format.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\pandas\io\formats\printing.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\numpy\lib\_npyio_impl.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\numpy\lib\_utils_impl.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\numpy\linalg\tests\test_linalg.py | Jupyter |  | 8888 | ✅ | ❌ | Test functions for linalg module |
| .venv\Lib\site-packages\nbformat\v1\convert.py | Jupyter |  | 8888 | ❌ | ❌ | Convert notebook to the v1 format. |
| .venv\Lib\site-packages\nbformat\v1\nbbase.py | Jupyter |  | 8888 | ❌ | ❌ | The basic dict based notebook format. |
| .venv\Lib\site-packages\nbformat\v1\nbjson.py | Jupyter |  | 8888 | ❌ | ❌ | Read and write notebooks in JSON format. |
| .venv\Lib\site-packages\nbformat\v1\rwbase.py | Jupyter |  | 8888 | ❌ | ❌ | Base classes and function for readers and writers. |
| .venv\Lib\site-packages\nbformat\v1\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | The main module for the v1 notebook format. |
| .venv\Lib\site-packages\nbformat\v2\convert.py | Jupyter |  | 8888 | ❌ | ❌ | Code for converting notebooks to and from the v2 format. |
| .venv\Lib\site-packages\nbformat\v2\nbbase.py | Jupyter |  | 8888 | ❌ | ❌ | The basic dict based notebook format. |
| .venv\Lib\site-packages\nbformat\v2\nbjson.py | Jupyter |  | 8888 | ❌ | ❌ | Read and write notebooks in JSON format. |
| .venv\Lib\site-packages\nbformat\v2\nbpy.py | Jupyter |  | 8888 | ❌ | ❌ | Read and write notebooks as regular .py files. |
| .venv\Lib\site-packages\nbformat\v2\nbxml.py | Jupyter |  | 8888 | ❌ | ❌ | REMOVED: Read and write notebook files as XML. |
| .venv\Lib\site-packages\nbformat\v2\rwbase.py | Jupyter |  | 8888 | ❌ | ❌ | Base classes and utilities for readers and writers. |
| .venv\Lib\site-packages\nbformat\v2\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | The main API for the v2 notebook format. |
| .venv\Lib\site-packages\nbformat\v3\convert.py | Jupyter |  | 8888 | ❌ | ❌ | Code for converting notebooks to and from the v2 format. |
| .venv\Lib\site-packages\nbformat\v3\nbbase.py | Jupyter |  | 8888 | ❌ | ❌ | The basic dict based notebook format. |
| .venv\Lib\site-packages\nbformat\v3\nbjson.py | Jupyter |  | 8888 | ❌ | ❌ | Read and write notebooks in JSON format. |
| .venv\Lib\site-packages\nbformat\v3\nbpy.py | Jupyter |  | 8888 | ❌ | ❌ | Read and write notebooks as regular .py files. |
| .venv\Lib\site-packages\nbformat\v3\rwbase.py | Jupyter |  | 8888 | ❌ | ❌ | Base classes and utilities for readers and writers. |
| .venv\Lib\site-packages\nbformat\v3\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | The main API for the v3 notebook format. |
| .venv\Lib\site-packages\nbformat\v4\convert.py | Jupyter |  | 8888 | ❌ | ❌ | Code for converting notebooks to and from v3. |
| .venv\Lib\site-packages\nbformat\v4\nbbase.py | Jupyter |  | 8888 | ❌ | ❌ | Python API for composing notebook elements |
| .venv\Lib\site-packages\nbformat\v4\nbjson.py | Jupyter |  | 8888 | ❌ | ❌ | Read and write notebooks in JSON format. |
| .venv\Lib\site-packages\nbformat\v4\rwbase.py | Jupyter |  | 8888 | ❌ | ❌ | Base classes and utilities for readers and writers. |
| .venv\Lib\site-packages\nbformat\v4\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | The main API for the v4 notebook format. |
| .venv\Lib\site-packages\nbconvert\exporters\html.py | Jupyter |  | 8888 | ❌ | ❌ | HTML Exporter class |
| .venv\Lib\site-packages\nbconvert\exporters\notebook.py | Jupyter |  | 8888 | ❌ | ❌ | NotebookExporter class |
| .venv\Lib\site-packages\nbconvert\exporters\pdf.py | Jupyter |  | 8888 | ❌ | ❌ | Export to PDF via latex |
| .venv\Lib\site-packages\nbconvert\exporters\qtpdf.py | Jupyter |  | 8888 | ❌ | ❌ | Export to PDF via a headless browser |
| .venv\Lib\site-packages\nbconvert\exporters\qtpng.py | Jupyter |  | 8888 | ❌ | ❌ | Export to PNG via a headless browser |
| .venv\Lib\site-packages\nbconvert\exporters\templateexporter.py | Jupyter |  | 8888 | ❌ | ❌ | This module defines TemplateExporter, a highly configurable converter |
| .venv\Lib\site-packages\nbconvert\exporters\webpdf.py | Jupyter |  | 8888 | ❌ | ❌ | Export to PDF via a headless browser |
| .venv\Lib\site-packages\nbconvert\filters\ansi.py | Jupyter |  | 8888 | ❌ | ❌ | Filters for processing ANSI colors within Jinja templates. |
| .venv\Lib\site-packages\nbconvert\filters\citation.py | Jupyter |  | 8888 | ❌ | ❌ | Citation handling for LaTeX output. |
| .venv\Lib\site-packages\nbconvert\filters\datatypefilter.py | Jupyter |  | 8888 | ❌ | ❌ | Filter used to select the first preferred output format available. |
| .venv\Lib\site-packages\nbconvert\filters\highlight.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\nbconvert\filters\latex.py | Jupyter |  | 8888 | ❌ | ❌ | Latex filters. |
| .venv\Lib\site-packages\nbconvert\filters\markdown.py | Jupyter |  | 8888 | ❌ | ❌ | Markdown filters |
| .venv\Lib\site-packages\nbconvert\filters\markdown_mistune.py | Jupyter |  | 8888 | ❌ | ❌ | Markdown filters with mistune |
| .venv\Lib\site-packages\nbconvert\filters\strings.py | Jupyter |  | 8888 | ❌ | ❌ | String filters. |
| .venv\Lib\site-packages\nbconvert\filters\widgetsdatatypefilter.py | Jupyter |  | 8888 | ❌ | ❌ | Filter used to select the first preferred output format available, |
| .venv\Lib\site-packages\nbconvert\postprocessors\base.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\nbconvert\preprocessors\base.py | Jupyter |  | 8888 | ❌ | ❌ | Base class for preprocessors |
| .venv\Lib\site-packages\nbconvert\preprocessors\clearmetadata.py | Jupyter |  | 8888 | ❌ | ❌ | Module containing a preprocessor that removes metadata from code cells |
| .venv\Lib\site-packages\nbconvert\preprocessors\clearoutput.py | Jupyter |  | 8888 | ❌ | ❌ | Module containing a preprocessor that removes the outputs from code cells |
| .venv\Lib\site-packages\nbconvert\preprocessors\coalescestreams.py | Jupyter |  | 8888 | ❌ | ❌ | Preprocessor for merging consecutive stream outputs for easier handling. |
| .venv\Lib\site-packages\nbconvert\preprocessors\csshtmlheader.py | Jupyter |  | 8888 | ❌ | ❌ | Module that pre-processes the notebook for export to HTML. |
| .venv\Lib\site-packages\nbconvert\preprocessors\execute.py | Jupyter |  | 8888 | ❌ | ❌ | Module containing a preprocessor that executes the code cells |
| .venv\Lib\site-packages\nbconvert\preprocessors\extractoutput.py | Jupyter |  | 8888 | ❌ | ❌ | A preprocessor that extracts all of the outputs from the |
| .venv\Lib\site-packages\nbconvert\preprocessors\latex.py | Jupyter |  | 8888 | ❌ | ❌ | Module that allows latex output notebooks to be conditioned before |
| .venv\Lib\site-packages\nbconvert\preprocessors\regexremove.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\nbconvert\preprocessors\tagremove.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\nbconvert\utils\exceptions.py | Jupyter |  | 8888 | ❌ | ❌ | NbConvert specific exceptions |
| .venv\Lib\site-packages\nbconvert\utils\lexers.py | Jupyter |  | 8888 | ❌ | ❌ | Deprecated as of 5.0; import from IPython.lib.lexers instead. |
| .venv\Lib\site-packages\nbconvert\utils\pandoc.py | Jupyter |  | 8888 | ❌ | ❌ | Utility for calling pandoc |
| .venv\Lib\site-packages\nbconvert\writers\debug.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\nbconvert\writers\files.py | Jupyter |  | 8888 | ❌ | ❌ | Contains writer for writing nbconvert output to filesystem. |
| .venv\Lib\site-packages\moviepy\video\io\display_in_notebook.py | Jupyter |  | 8888 | ❌ | ❌ | Implements ``display_in_notebook``, a function to embed images/videos/audio in the |
| .venv\Lib\site-packages\matplotlib\backends\backend_nbagg.py | Jupyter |  | 8888 | ❌ | ❌ | Interactive figures in the IPython notebook. |
| .venv\Lib\site-packages\matplotlib\backends\backend_webagg.py | Jupyter |  | 8888 | ❌ | ❌ | Displays Agg images in the browser, with interactivity. |
| .venv\Lib\site-packages\matplotlib\backends\registry.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\backends\_backend_gtk.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\testing\__init__.py | Jupyter |  | 8888 | ✅ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\tests\test_backend_inline.py | Jupyter |  | 8888 | ❌ | ❌ | This code can be removed when Python 3.12, the latest version supported by |
| .venv\Lib\site-packages\matplotlib\tests\test_backend_nbagg.py | Jupyter |  | 8888 | ❌ | ❌ | From https://blog.thedataincubator.com/2016/06/testing-jupyter-notebooks/ |
| .venv\Lib\site-packages\matplotlib\tests\test_backend_webagg.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\matplotlib\tests\test_pyplot.py | Jupyter |  | 8888 | ✅ | ❌ | Test that pyplot_summary lists all the plot functions. |
| .venv\Lib\site-packages\markdownlit\extensions\at_sign.py | Streamlit |  | 8501 | ❌ | ✅ | Transforms '@(icon)(label)(url)' into HTML. |
| .venv\Lib\site-packages\jupyter_server\auth\identity.py | Jupyter |  | 8888 | ❌ | ❌ | Identity Provider interface |
| .venv\Lib\site-packages\jupyter_server\extension\application.py | Jupyter |  | 8888 | ❌ | ❌ | An extension application. |
| .venv\Lib\site-packages\jupyter_console\tests\test_console.py | Jupyter |  | 8888 | ✅ | ❌ | Tests for two-process terminal frontend |
| .venv\Lib\site-packages\jupyter_console\tests\test_image_handler.py | Jupyter |  | 8888 | ❌ | ❌ | A testing shell class that doesn't attempt to communicate with the kernel |
| .venv\Lib\site-packages\jupyter_console\tests\writetofile.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\jupyter_client\ssh\forward.py | Jupyter |  | 8888 | ❌ | ❌ | Sample script showing how to do local port forwarding over paramiko. |
| .venv\Lib\site-packages\jupyter_client\ssh\tunnel.py | Jupyter |  | 8888 | ❌ | ❌ | Basic ssh tunnel utilities, and convenience functions for tunneling |
| .venv\Lib\site-packages\jedi\api\interpreter.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\jedi\api\replstartup.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\jedi\plugins\registry.py | Flask |  | 5000 | ❌ | ❌ |  |
| .venv\Lib\site-packages\ipywidgets\widgets\interaction.py | Jupyter |  | 8888 | ❌ | ❌ | Interact with functions using widgets. |
| .venv\Lib\site-packages\ipywidgets\widgets\widget.py | Jupyter |  | 8888 | ❌ | ❌ | Base Widget class.  Allows user to create widgets in the back-end that render |
| .venv\Lib\site-packages\ipywidgets\widgets\widget_output.py | Jupyter |  | 8888 | ❌ | ❌ | Output class. |
| .venv\Lib\site-packages\ipywidgets\widgets\tests\test_widget.py | Jupyter |  | 8888 | ❌ | ❌ | Test Widget. |
| .venv\Lib\site-packages\ipywidgets\widgets\tests\test_widget_output.py | Jupyter |  | 8888 | ❌ | ❌ | Context manager that monkeypatches get_ipython and clear_output |
| .venv\Lib\site-packages\IPython\core\alias.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\application.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\async_helpers.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\autocall.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\builtin_trap.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\compilerop.py | Jupyter |  | 8888 | ❌ | ❌ | Compiler tools with improved interactive support. |
| .venv\Lib\site-packages\IPython\core\completer.py | Jupyter |  | 8888 | ❌ | ❌ | Completion for IPython. |
| .venv\Lib\site-packages\IPython\core\completerlib.py | Jupyter |  | 8888 | ❌ | ❌ | Implementations for various useful completers. |
| .venv\Lib\site-packages\IPython\core\crashhandler.py | Jupyter |  | 8888 | ❌ | ❌ | sys.excepthook for IPython itself, leaves a detailed report on disk. |
| .venv\Lib\site-packages\IPython\core\debugger.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\debugger_backport.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\display.py | Jupyter |  | 8888 | ❌ | ❌ | Top-level display functions for displaying object in different formats. |
| .venv\Lib\site-packages\IPython\core\displayhook.py | Jupyter |  | 8888 | ❌ | ❌ | Displayhook for IPython. |
| .venv\Lib\site-packages\IPython\core\displaypub.py | Jupyter |  | 8888 | ❌ | ❌ | An interface for publishing rich data to frontends. |
| .venv\Lib\site-packages\IPython\core\display_functions.py | Jupyter |  | 8888 | ❌ | ❌ | Top-level display functions for displaying object in different formats. |
| .venv\Lib\site-packages\IPython\core\display_trap.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\doctb.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\error.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\events.py | Jupyter |  | 8888 | ❌ | ❌ | Infrastructure for registering and firing callbacks on application events. |
| .venv\Lib\site-packages\IPython\core\extensions.py | Jupyter |  | 8888 | ❌ | ❌ | A class for managing IPython extensions. |
| .venv\Lib\site-packages\IPython\core\formatters.py | Jupyter |  | 8888 | ❌ | ❌ | Display formatters. |
| .venv\Lib\site-packages\IPython\core\getipython.py | Jupyter |  | 8888 | ❌ | ❌ | Simple function to call to get the current InteractiveShell instance |
| .venv\Lib\site-packages\IPython\core\guarded_eval.py | Jupyter |  | 8888 | ❌ | ❌ | Get unbound method for given bound method. |
| .venv\Lib\site-packages\IPython\core\history.py | Jupyter |  | 8888 | ❌ | ❌ | History related magics and functionality |
| .venv\Lib\site-packages\IPython\core\historyapp.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\hooks.py | Jupyter |  | 8888 | ❌ | ❌ | Hooks for IPython. |
| .venv\Lib\site-packages\IPython\core\inputtransformer2.py | Jupyter |  | 8888 | ❌ | ❌ | Input transformer machinery to support IPython special syntax. |
| .venv\Lib\site-packages\IPython\core\interactiveshell.py | Jupyter |  | 8888 | ❌ | ❌ | Main IPython class. |
| .venv\Lib\site-packages\IPython\core\logger.py | Jupyter |  | 8888 | ❌ | ❌ | Logger class for IPython's logging facilities. |
| .venv\Lib\site-packages\IPython\core\macro.py | Jupyter |  | 8888 | ❌ | ❌ | Support for interactive macros in IPython |
| .venv\Lib\site-packages\IPython\core\magic.py | Jupyter |  | 8888 | ❌ | ❌ | Magic functions for InteractiveShell. |
| .venv\Lib\site-packages\IPython\core\magic_arguments.py | Jupyter |  | 8888 | ❌ | ❌ | A really cool magic command. |
| .venv\Lib\site-packages\IPython\core\oinspect.py | Jupyter |  | 8888 | ❌ | ❌ | Tools for inspecting Python objects. |
| .venv\Lib\site-packages\IPython\core\page.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\payload.py | Jupyter |  | 8888 | ❌ | ❌ | Payload system for IPython. |
| .venv\Lib\site-packages\IPython\core\payloadpage.py | Jupyter |  | 8888 | ❌ | ❌ | A payload based version of page. |
| .venv\Lib\site-packages\IPython\core\prefilter.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\profileapp.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\profiledir.py | Jupyter |  | 8888 | ❌ | ❌ | An object for managing IPython profile directories. |
| .venv\Lib\site-packages\IPython\core\pylabtools.py | Jupyter |  | 8888 | ❌ | ❌ | Pylab (matplotlib) support utilities. |
| .venv\Lib\site-packages\IPython\core\release.py | Jupyter |  | 8888 | ❌ | ❌ | Release data for the IPython project. |
| .venv\Lib\site-packages\IPython\core\shellapp.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\splitinput.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\tbtools.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\tips.py | Jupyter |  | 8888 | ❌ | ❌ | (month, day) |
| .venv\Lib\site-packages\IPython\core\ultratb.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\usage.py | Jupyter |  | 8888 | ❌ | ❌ | Usage information for the main IPython applications. |
| .venv\Lib\site-packages\IPython\extensions\autoreload.py | Jupyter |  | 8888 | ❌ | ❌ | IPython extension to reload modules before executing user code. |
| .venv\Lib\site-packages\IPython\extensions\storemagic.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\extensions\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | This directory is meant for IPython extensions. |
| .venv\Lib\site-packages\IPython\external\qt_for_kernel.py | Jupyter |  | 8888 | ❌ | ❌ | Import Qt in a manner suitable for an IPython kernel. |
| .venv\Lib\site-packages\IPython\external\qt_loaders.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\external\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\lib\backgroundjobs.py | Jupyter |  | 8888 | ❌ | ❌ | Manage background (threaded) jobs conveniently from an interactive shell. |
| .venv\Lib\site-packages\IPython\lib\clipboard.py | Jupyter |  | 8888 | ❌ | ❌ | Utilities for accessing the platform's clipboard. |
| .venv\Lib\site-packages\IPython\lib\deepreload.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\lib\demo.py | Jupyter |  | 8888 | ❌ | ❌ | Module for interactive demos using IPython. |
| .venv\Lib\site-packages\IPython\lib\display.py | Jupyter |  | 8888 | ❌ | ❌ | Various display related classes. |
| .venv\Lib\site-packages\IPython\lib\editorhooks.py | Jupyter |  | 8888 | ❌ | ❌ | 'editor' hooks for common editors that work well with ipython |
| .venv\Lib\site-packages\IPython\lib\guisupport.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\lib\latextools.py | Jupyter |  | 8888 | ❌ | ❌ | Tools for handling LaTeX. |
| .venv\Lib\site-packages\IPython\lib\lexers.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\lib\pretty.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\lib\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\sphinxext\custom_doctests.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\sphinxext\ipython_directive.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\terminal\debugger.py | Jupyter |  | 8888 | ❌ | ❌ | Standalone IPython debugger. |
| .venv\Lib\site-packages\IPython\terminal\embed.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\terminal\interactiveshell.py | Jupyter |  | 8888 | ❌ | ❌ | IPython terminal interface using prompt_toolkit |
| .venv\Lib\site-packages\IPython\terminal\ipapp.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\terminal\magics.py | Jupyter |  | 8888 | ❌ | ❌ | Extra magics for terminal use. |
| .venv\Lib\site-packages\IPython\terminal\prompts.py | Jupyter |  | 8888 | ❌ | ❌ | Terminal input and output prompts. |
| .venv\Lib\site-packages\IPython\terminal\ptutils.py | Jupyter |  | 8888 | ❌ | ❌ | prompt-toolkit utilities |
| .venv\Lib\site-packages\IPython\testing\globalipapp.py | Jupyter |  | 8888 | ❌ | ❌ | Global IPython app to support test running. |
| .venv\Lib\site-packages\IPython\testing\ipunittest.py | Jupyter |  | 8888 | ❌ | ❌ | Experimental code for cleaner support of IPython syntax with unittest. |
| .venv\Lib\site-packages\IPython\testing\skipdoctest.py | Jupyter |  | 8888 | ❌ | ❌ | Decorators marks that a doctest should be skipped. |
| .venv\Lib\site-packages\IPython\testing\tools.py | Jupyter |  | 8888 | ❌ | ❌ | Generic testing tools. |
| .venv\Lib\site-packages\IPython\testing\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Testing support (tools to test IPython itself). |
| .venv\Lib\site-packages\IPython\utils\capture.py | Jupyter |  | 8888 | ❌ | ❌ | IO capturing utilities. |
| .venv\Lib\site-packages\IPython\utils\coloransi.py | Jupyter |  | 8888 | ❌ | ❌ | Deprecated/should be removed, but we break older version of ipyparallel |
| .venv\Lib\site-packages\IPython\utils\contexts.py | Jupyter |  | 8888 | ❌ | ❌ | Miscellaneous context managers. |
| .venv\Lib\site-packages\IPython\utils\data.py | Jupyter |  | 8888 | ❌ | ❌ | Utilities for working with data structures like lists, dicts and tuples. |
| .venv\Lib\site-packages\IPython\utils\decorators.py | Jupyter |  | 8888 | ❌ | ❌ | Decorators that don't go anywhere else. |
| .venv\Lib\site-packages\IPython\utils\dir2.py | Jupyter |  | 8888 | ❌ | ❌ | A fancy version of Python's builtin :func:`dir` function. |
| .venv\Lib\site-packages\IPython\utils\encoding.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\eventful.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\frame.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\generics.py | Jupyter |  | 8888 | ❌ | ❌ | Generic functions for extending IPython. |
| .venv\Lib\site-packages\IPython\utils\importstring.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\io.py | Jupyter | launch_evolution_3d_view.bat | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\ipstruct.py | Jupyter |  | 8888 | ❌ | ❌ | A dict subclass that supports attribute style access. |
| .venv\Lib\site-packages\IPython\utils\jsonutil.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\log.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\module_paths.py | Jupyter |  | 8888 | ❌ | ❌ | Utility functions for finding modules |
| .venv\Lib\site-packages\IPython\utils\path.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\process.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\PyColorize.py | Jupyter |  | 8888 | ❌ | ❌ | generate the leading arrow in front of traceback or debugger |
| .venv\Lib\site-packages\IPython\utils\sentinel.py | Jupyter |  | 8888 | ❌ | ❌ | Sentinel class for constants with useful reprs |
| .venv\Lib\site-packages\IPython\utils\strdispatch.py | Jupyter |  | 8888 | ❌ | ❌ | String dispatch class to match regexps and dispatch commands. |
| .venv\Lib\site-packages\IPython\utils\sysinfo.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\terminal.py | Jupyter | launch_dashboard_quant_terminal.bat | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\text.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\timing.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\utils\tokenutil.py | Jupyter |  | 8888 | ❌ | ❌ | Token-related utilities |
| .venv\Lib\site-packages\IPython\utils\wildcard.py | Jupyter |  | 8888 | ❌ | ❌ | Support for wildcard pattern matching in object inspection. |
| .venv\Lib\site-packages\IPython\utils\_process_cli.py | Jupyter |  | 8888 | ❌ | ❌ | cli-specific implementation of process utilities. |
| .venv\Lib\site-packages\IPython\utils\_process_common.py | Jupyter |  | 8888 | ❌ | ❌ | Common utilities for the various process_* implementations. |
| .venv\Lib\site-packages\IPython\utils\_process_posix.py | Jupyter |  | 8888 | ❌ | ❌ | Posix-specific implementation of process utilities. |
| .venv\Lib\site-packages\IPython\utils\_process_win32.py | Jupyter |  | 8888 | ❌ | ❌ | Windows-specific implementation of process utilities. |
| .venv\Lib\site-packages\IPython\utils\_process_win32_controller.py | Jupyter |  | 8888 | ❌ | ❌ | Windows-specific implementation of process utilities with direct WinAPI. |
| .venv\Lib\site-packages\IPython\testing\plugin\dtexample.py | Jupyter |  | 8888 | ❌ | ❌ | Simple example using doctests. |
| .venv\Lib\site-packages\IPython\testing\plugin\ipdoctest.py | Jupyter |  | 8888 | ❌ | ❌ | Nose Plugin that supports IPython doctests. |
| .venv\Lib\site-packages\IPython\testing\plugin\pytest_ipdoctest.py | Jupyter |  | 8888 | ✅ | ❌ | Discover and run ipdoctests in modules and test files. |
| .venv\Lib\site-packages\IPython\testing\plugin\setup.py | Jupyter |  | 8888 | ❌ | ❌ | A Nose plugin to support IPython doctests. |
| .venv\Lib\site-packages\IPython\testing\plugin\simple.py | Jupyter |  | 8888 | ❌ | ❌ | Simple example using doctests. |
| .venv\Lib\site-packages\IPython\terminal\pt_inputhooks\asyncio.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\terminal\pt_inputhooks\glut.py | Jupyter |  | 8888 | ❌ | ❌ | GLUT Input hook for interactive use with prompt_toolkit |
| .venv\Lib\site-packages\IPython\terminal\pt_inputhooks\pyglet.py | Jupyter |  | 8888 | ❌ | ❌ | Enable pyglet to be used interactively with prompt_toolkit |
| .venv\Lib\site-packages\IPython\terminal\pt_inputhooks\qt.py | Jupyter |  | 8888 | ❌ | ❌ | If we create a QApplication, QEventLoop, or a QTimer, keep a reference to them |
| .venv\Lib\site-packages\IPython\terminal\pt_inputhooks\wx.py | Jupyter |  | 8888 | ❌ | ❌ | Enable wxPython to be used interactively in prompt_toolkit |
| .venv\Lib\site-packages\IPython\terminal\pt_inputhooks\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Register the function *inputhook* as an event loop integration. |
| .venv\Lib\site-packages\IPython\terminal\shortcuts\auto_suggest.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\terminal\shortcuts\filters.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\terminal\shortcuts\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\extensions\deduperreload\deduperreload.py | Jupyter |  | 8888 | ❌ | ❌ | Returns the module's file path, or the empty string if it's inaccessible |
| .venv\Lib\site-packages\IPython\core\magics\ast_mod.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\IPython\core\magics\auto.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of magic functions that control various automatic behaviors. |
| .venv\Lib\site-packages\IPython\core\magics\basic.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of basic magic functions. |
| .venv\Lib\site-packages\IPython\core\magics\code.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of code management magic functions. |
| .venv\Lib\site-packages\IPython\core\magics\config.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of configuration-related magic functions. |
| .venv\Lib\site-packages\IPython\core\magics\display.py | Jupyter |  | 8888 | ❌ | ❌ | Simple magics for display formats |
| .venv\Lib\site-packages\IPython\core\magics\execution.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of execution-related magic functions. |
| .venv\Lib\site-packages\IPython\core\magics\extension.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of magic functions for the extension machinery. |
| .venv\Lib\site-packages\IPython\core\magics\history.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of magic functions related to History. |
| .venv\Lib\site-packages\IPython\core\magics\logging.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of magic functions for IPython's own logging. |
| .venv\Lib\site-packages\IPython\core\magics\namespace.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of namespace-related magic functions. |
| .venv\Lib\site-packages\IPython\core\magics\osm.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of magic functions for interaction with the OS. |
| .venv\Lib\site-packages\IPython\core\magics\packaging.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of packaging-related magic functions. |
| .venv\Lib\site-packages\IPython\core\magics\pylab.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of magic functions for matplotlib/pylab support. |
| .venv\Lib\site-packages\IPython\core\magics\script.py | Jupyter |  | 8888 | ❌ | ❌ | Magic functions for running cells in various scripts. |
| .venv\Lib\site-packages\IPython\core\magics\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Implementation of all the magic functions built into IPython. |
| .venv\Lib\site-packages\ipykernel\comm\comm.py | Jupyter |  | 8888 | ❌ | ❌ | Base class for a Comm |
| .venv\Lib\site-packages\ipykernel\comm\manager.py | Jupyter |  | 8888 | ❌ | ❌ | Base class to manage comms |
| .venv\Lib\site-packages\ipykernel\gui\gtk3embed.py | Jupyter |  | 8888 | ❌ | ❌ | GUI support for the IPython ZeroMQ kernel - GTK toolkit support. |
| .venv\Lib\site-packages\ipykernel\gui\gtkembed.py | Jupyter |  | 8888 | ❌ | ❌ | GUI support for the IPython ZeroMQ kernel - GTK toolkit support. |
| .venv\Lib\site-packages\ipykernel\gui\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | GUI support for the IPython ZeroMQ kernel. |
| .venv\Lib\site-packages\ipykernel\inprocess\blocking.py | Jupyter |  | 8888 | ❌ | ❌ | Implements a fully blocking kernel client. |
| .venv\Lib\site-packages\ipykernel\inprocess\channels.py | Jupyter |  | 8888 | ❌ | ❌ | A kernel client for in-process kernels. |
| .venv\Lib\site-packages\ipykernel\inprocess\client.py | Jupyter |  | 8888 | ❌ | ❌ | A client for in-process kernels. |
| .venv\Lib\site-packages\ipykernel\inprocess\ipkernel.py | Jupyter |  | 8888 | ❌ | ❌ | An in-process kernel |
| .venv\Lib\site-packages\ipykernel\inprocess\manager.py | Jupyter |  | 8888 | ❌ | ❌ | A kernel manager for in-process kernels. |
| .venv\Lib\site-packages\ipykernel\inprocess\socket.py | Jupyter |  | 8888 | ❌ | ❌ | Defines a dummy socket implementing (part of) the zmq.Socket interface. |
| .venv\Lib\site-packages\ipykernel\pylab\backend_inline.py | Jupyter |  | 8888 | ❌ | ❌ | A matplotlib backend for publishing figures via display_data |
| .venv\Lib\site-packages\ipykernel\pylab\config.py | Jupyter |  | 8888 | ❌ | ❌ | Configurable for configuring the IPython inline backend |
| .venv\Lib\site-packages\hvplot\plotting\core.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\hvplot\tests\testinteractive.py | Panel |  | 5010 | ❌ | ✅ | noqa |
| .venv\Lib\site-packages\hvplot\tests\testpanel.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\hvplot\tests\testutil.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\core\options.py | Jupyter |  | 8888 | ❌ | ❌ | Options and OptionTrees allow different classes of options |
| .venv\Lib\site-packages\holoviews\element\comparison.py | Jupyter |  | 8888 | ❌ | ❌ | Helper classes for comparing the equality of two HoloViews objects. |
| .venv\Lib\site-packages\holoviews\ipython\archive.py | Jupyter |  | 8888 | ❌ | ❌ | Implements NotebookArchive used to automatically capture notebook data |
| .venv\Lib\site-packages\holoviews\ipython\display_hooks.py | Jupyter |  | 8888 | ❌ | ❌ | Definition and registration of display hooks for the IPython Notebook. |
| .venv\Lib\site-packages\holoviews\ipython\magics.py | Jupyter |  | 8888 | ❌ | ❌ | Pretty print the current element options |
| .venv\Lib\site-packages\holoviews\ipython\preprocessors.py | Jupyter |  | 8888 | ❌ | ❌ | Prototype demo: |
| .venv\Lib\site-packages\holoviews\ipython\widgets.py | Jupyter |  | 8888 | ❌ | ❌ | A simple text progress bar suitable for both the IPython notebook |
| .venv\Lib\site-packages\holoviews\ipython\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Display the full traceback after an abbreviated traceback has occurred. |
| .venv\Lib\site-packages\holoviews\plotting\plot.py | Jupyter |  | 8888 | ❌ | ❌ | Public API for all plots supported by HoloViews, regardless of |
| .venv\Lib\site-packages\holoviews\plotting\renderer.py | Panel |  | 5010 | ❌ | ✅ | Public API for all plotting renderers supported by HoloViews, |
| .venv\Lib\site-packages\holoviews\plotting\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | HoloViews plotting sub-system that defines the interface to be used by |
| .venv\Lib\site-packages\holoviews\tests\conftest.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\tests\test_selection.py | Panel |  | 5010 | ❌ | ✅ | ff0000" |
| .venv\Lib\site-packages\holoviews\tests\test_streams.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\util\parser.py | Jupyter |  | 8888 | ❌ | ❌ | The magics offered by the HoloViews IPython extension are powerful and |
| .venv\Lib\site-packages\holoviews\util\warnings.py | Jupyter |  | 8888 | ❌ | ❌ | Find the first place in the stack that is not inside Holoviews and Param. |
| .venv\Lib\site-packages\holoviews\util\_versions.py | Panel |  | 5010 | ❌ | ✅ | Data |
| .venv\Lib\site-packages\holoviews\util\__init__.py | Panel |  | 5010 | ❌ | ✅ | Copies the notebooks to the supplied path. |
| .venv\Lib\site-packages\holoviews\tests\core\test_dynamic.py | Panel |  | 5010 | ❌ | ✅ | Tests that Callable memoizes unchanged callbacks |
| .venv\Lib\site-packages\holoviews\tests\ipython\test_displayhooks.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\holoviews\tests\ipython\test_magics.py | Jupyter |  | 8888 | ✅ | ❌ | TODO: Should set it back |
| .venv\Lib\site-packages\holoviews\tests\ipython\test_notebooks.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\holoviews\tests\util\test_help.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\holoviews\tests\util\test_init.py | Jupyter |  | 8888 | ❌ | ❌ | \ |
| .venv\Lib\site-packages\holoviews\tests\ui\bokeh\test_callback.py | Panel |  | 5010 | ❌ | ✅ | Helper method to perform point selection based on tool type. |
| .venv\Lib\site-packages\holoviews\tests\ui\bokeh\test_hover.py | Panel |  | 5010 | ✅ | ✅ | Hover over the plot |
| .venv\Lib\site-packages\holoviews\tests\plotting\bokeh\test_elementplot.py | Panel |  | 5010 | ❌ | ✅ | Test `apply_hard_bounds` with a single element. |
| .venv\Lib\site-packages\holoviews\tests\plotting\bokeh\test_overlayplot.py | Panel |  | 5010 | ❌ | ✅ | def test_hover_tool_overlay_renderers(self): |
| .venv\Lib\site-packages\holoviews\tests\plotting\bokeh\test_renderer.py | Panel |  | 5010 | ❌ | ✅ | 444444'}} |
| .venv\Lib\site-packages\holoviews\tests\plotting\matplotlib\test_renderer.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\tests\plotting\plotly\test_dash.py | Dash |  | 8050 | ❌ | ✅ | noqa: F401 |
| .venv\Lib\site-packages\holoviews\tests\plotting\plotly\test_dynamic.py | Panel |  | 5010 | ❌ | ✅ | Build stream |
| .venv\Lib\site-packages\holoviews\tests\plotting\plotly\test_renderer.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\plotting\bokeh\callbacks.py | Panel |  | 5010 | ❌ | ✅ | Provides a baseclass to define callbacks, which return data from |
| .venv\Lib\site-packages\holoviews\plotting\bokeh\renderer.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\holoviews\plotting\mpl\renderer.py | Jupyter |  | 8888 | ❌ | ❌ | Exporter used to render data from matplotlib, either to a stream |
| .venv\Lib\site-packages\holoviews\plotting\plotly\dash.py | Dash | launch_alert_dashboard.bat | 8050 | ❌ | ✅ | Convert a HoloViews plotly plot to a plotly.py Figure. |
| .venv\Lib\site-packages\holoviews\plotting\plotly\renderer.py | Panel |  | 5010 | ❌ | ✅ | Custom Plotly pane constructor for use by the HoloViews Pane. |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\crossfilter.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\game_of_life.py | Panel |  | 5010 | ❌ | ✅ | Set up plot which advances on counter and adds pattern on tap |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\gapminder.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\streaming_psutil.py | Panel |  | 5010 | ❌ | ✅ | Define functions to get memory and CPU usage |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\flask\flask_app.py | Flask |  | 5000 | ❌ | ❌ | locally creates a page |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\flask\holoviews_app.py | Panel |  | 5010 | ❌ | ✅ |  |
| .venv\Lib\site-packages\holoviews\core\util\__init__.py | Jupyter |  | 8888 | ❌ | ❌ | Set of boolean configuration values to change HoloViews' global |
| .venv\Lib\site-packages\docutils\writers\odf_odt\__init__.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydevconsole.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhook.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookglut.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookgtk.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookgtk3.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookpyglet.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookqt4.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookqt5.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookqt6.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhooktk.py | Jupyter |  | 8888 | ❌ | ❌ | encoding: utf-8 |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\inputhookwx.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\matplotlibtools.py | Jupyter |  | 8888 | ❌ | ❌ | Return the gui and mpl backend. |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\qt_for_kernel.py | Jupyter |  | 8888 | ❌ | ❌ | Import Qt in a manner suitable for an IPython kernel. |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\pydev_ipython\qt_loaders.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydevd_bundle\pydevd_process_net_command_json.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydevd_bundle\pydevd_xml.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydev_bundle\pydev_console_utils.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydev_bundle\pydev_ipython_console.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydev_bundle\pydev_ipython_console_011.py | Jupyter |  | 8888 | ❌ | ❌ | Interface to TerminalInteractiveShell for PyDev Interactive Console frontend |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydev_bundle\pydev_umd.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydev_bundle\pydev_versioncheck.py | Jupyter |  | 8888 | ❌ | ❌ | Return True if running Python is suitable for GUI Event Integration and deeper IPython integration |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydev_bundle\_pydev_completer.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\debugpy\_vendored\pydevd\_pydevd_bundle\_debug_adapter\pydevd_schema.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\bokeh\io\notebook.py | Jupyter |  | 8888 | ❌ | ❌ | Callable to configure Bokeh's show method when a proxy must be |
| .venv\Lib\site-packages\bokeh\util\info.py | Jupyter |  | 8888 | ❌ | ❌ | Print version information about Bokeh, Python, the operating system |
| .venv\Lib\site-packages\bokeh\command\subcommands\info.py | Jupyter |  | 8888 | ❌ | ❌ | ----------------------------------------------------------------------------- |
| .venv\Lib\site-packages\bokeh\application\handlers\notebook.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\altair\utils\core.py | Jupyter |  | 8888 | ❌ | ❌ | Utility routines. |
| .venv\Lib\site-packages\altair\utils\display.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\altair\utils\mimebundle.py | Jupyter |  | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\altair\vegalite\v6\api.py | Jupyter | launch_api_rest.bat | 8888 | ❌ | ❌ |  |
| .venv\Lib\site-packages\altair\vegalite\v6\display.py | Jupyter |  | 8888 | ❌ | ❌ | \ |
