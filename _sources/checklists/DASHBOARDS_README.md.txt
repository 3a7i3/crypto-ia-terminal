# Dashboards & Visualisation Apps — Crypto AI Terminal

Ce dépôt contient plusieurs dashboards interactifs pour la supervision, l’analyse et le pilotage des systèmes quantitatifs. Chaque dashboard est automatiquement exclu des tests unitaires (pytest) et dispose d’un script de lancement rapide sous Windows.

## Table des Dashboards et Scripts de Lancement

| Dashboard / App | Framework | Script de lancement | Port par défaut | Description rapide |
|-----------------|-----------|---------------------|-----------------|--------------------|
| .venv\Lib\site-packages\holoviews\plotting\plotly\dash.py | Dash | launch_alert_dashboard.bat | 8050 | Convert a HoloViews plotly plot to a plotly.py Figure. |
| .venv\Lib\site-packages\holoviews\tests\plotting\plotly\test_dash.py | Dash | launch_test_dash.bat | 8050 | noqa: F401 |
| quant-trading-system\dashboard\dash_app.py | Dash | launch_dash_app.bat | 8050 |  |
| tests\test_alert_dashboard_functional.py | Dash | launch_test_alert_dashboard_functional.bat | 8050 | Teste le filtrage par module dans le dashboard. |
| .venv\Lib\site-packages\fastapi\__init__.py | FastAPI | launch___init__.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\applications.py | FastAPI | launch_applications.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\background.py | FastAPI | launch_background.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\datastructures.py | FastAPI | launch_datastructures.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\dependencies\utils.py | FastAPI | launch_utils.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\encoders.py | FastAPI | launch_encoders.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\exceptions.py | FastAPI | launch_exceptions.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\openapi\docs.py | FastAPI | launch_docs.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\openapi\utils.py | FastAPI | launch_utils.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\param_functions.py | FastAPI | launch_param_functions.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\params.py | FastAPI | launch_params.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\responses.py | FastAPI | launch_responses.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\routing.py | FastAPI | launch_routing.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\security\api_key.py | FastAPI | launch_api_key.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\security\http.py | FastAPI | launch_http.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\security\oauth2.py | FastAPI | launch_oauth2.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\security\open_id_connect_url.py | FastAPI | launch_open_id_connect_url.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\sse.py | FastAPI | launch_sse.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\fastapi\utils.py | FastAPI | launch_utils.bat | 8080 |  |
| .venv\Lib\site-packages\panel\io\fastapi.py | FastAPI | launch_fastapi.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\pydantic\_internal\_generate_schema.py | FastAPI | launch__generate_schema.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\pydantic\config.py | FastAPI | launch_config.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\pydantic\fields.py | FastAPI | launch_fields.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\pydantic\type_adapter.py | FastAPI | launch_type_adapter.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\streamlit\web\server\starlette\starlette_app.py | FastAPI | launch_starlette_app.bat | 8080 | API FastAPI |
| crypto_quant_v16\supervision\dashboard_api.py | FastAPI | launch_dashboard_api.bat | 8080 | API FastAPI |
| my_trading_system\ui\dashboard_fastapi.py | FastAPI | launch_dashboard_fastapi.bat | 8080 | API FastAPI |
| quant-trading-system\api\rest_api.py | FastAPI | launch_rest_api.bat | 8080 | API FastAPI |
| quant-trading-system\api\websocket_handler.py | FastAPI | launch_websocket_handler.bat | 8080 | API FastAPI |
| supervision\api_rest.py | FastAPI | launch_api_rest.bat | 8080 | API FastAPI |
| supervision\botdoctor_api.py | FastAPI | launch_botdoctor_api.bat | 8080 | API FastAPI |
| supervision\monitoring_api.py | FastAPI | launch_monitoring_api.bat | 8080 | API FastAPI |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\crossfilter.py | Panel | launch_crossfilter.bat | 5010 |  |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\game_of_life.py | Panel | launch_game_of_life.bat | 5010 | Set up plot which advances on counter and adds pattern on tap |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\gapminder.py | Panel | launch_gapminder.bat | 5010 |  |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\bokeh\streaming_psutil.py | Panel | launch_streaming_psutil.bat | 5010 | Define functions to get memory and CPU usage |
| .venv\Lib\site-packages\holoviews\examples\gallery\apps\flask\holoviews_app.py | Panel | launch_holoviews_app.bat | 5010 |  |
| .venv\Lib\site-packages\holoviews\plotting\bokeh\callbacks.py | Panel | launch_callbacks.bat | 5010 | Provides a baseclass to define callbacks, which return data from |
| .venv\Lib\site-packages\holoviews\plotting\plotly\renderer.py | Panel | launch_renderer.bat | 5010 | Custom Plotly pane constructor for use by the HoloViews Pane. |
| .venv\Lib\site-packages\holoviews\plotting\renderer.py | Panel | launch_renderer.bat | 5010 | Public API for all plotting renderers supported by HoloViews, |
| .venv\Lib\site-packages\holoviews\pyodide.py | Panel | launch_pyodide.bat | 5010 | Used to render elements to an image format (svg or png) if requested |
| .venv\Lib\site-packages\holoviews\tests\conftest.py | Panel | launch_conftest.bat | 5010 |  |
| .venv\Lib\site-packages\holoviews\tests\core\test_dynamic.py | Panel | launch_test_dynamic.bat | 5010 | Tests that Callable memoizes unchanged callbacks |
| .venv\Lib\site-packages\holoviews\tests\plotting\bokeh\test_elementplot.py | Panel | launch_test_elementplot.bat | 5010 | Test `apply_hard_bounds` with a single element. |
| .venv\Lib\site-packages\holoviews\tests\plotting\bokeh\test_overlayplot.py | Panel | launch_test_overlayplot.bat | 5010 | def test_hover_tool_overlay_renderers(self): |
| .venv\Lib\site-packages\holoviews\tests\plotting\bokeh\test_renderer.py | Panel | launch_test_renderer.bat | 5010 | 444444'}} |
| .venv\Lib\site-packages\holoviews\tests\plotting\matplotlib\test_renderer.py | Panel | launch_test_renderer.bat | 5010 |  |
| .venv\Lib\site-packages\holoviews\tests\plotting\plotly\test_dynamic.py | Panel | launch_test_dynamic.bat | 5010 | Build stream |
| .venv\Lib\site-packages\holoviews\tests\plotting\plotly\test_renderer.py | Panel | launch_test_renderer.bat | 5010 |  |
| .venv\Lib\site-packages\holoviews\tests\test_selection.py | Panel | launch_test_selection.bat | 5010 | ff0000" |
| .venv\Lib\site-packages\holoviews\tests\test_streams.py | Panel | launch_test_streams.bat | 5010 |  |
| .venv\Lib\site-packages\holoviews\tests\ui\bokeh\test_callback.py | Panel | launch_test_callback.bat | 5010 | Helper method to perform point selection based on tool type. |
| .venv\Lib\site-packages\holoviews\tests\ui\bokeh\test_hover.py | Panel | launch_test_hover.bat | 5010 | Hover over the plot |
| .venv\Lib\site-packages\holoviews\util\__init__.py | Panel | launch___init__.bat | 5010 | Copies the notebooks to the supplied path. |
| .venv\Lib\site-packages\holoviews\util\_versions.py | Panel | launch__versions.bat | 5010 | Data |
| .venv\Lib\site-packages\hvplot\__init__.py | Panel | launch___init__.bat | 5010 |  |
| .venv\Lib\site-packages\hvplot\fugue.py | Panel | launch_fugue.bat | 5010 |  |
| .venv\Lib\site-packages\hvplot\interactive.py | Panel | launch_interactive.bat | 5010 |  |
| .venv\Lib\site-packages\hvplot\plotting\core.py | Panel | launch_core.bat | 5010 |  |
| .venv\Lib\site-packages\hvplot\tests\testinteractive.py | Panel | launch_testinteractive.bat | 5010 | noqa |
| .venv\Lib\site-packages\hvplot\tests\testpanel.py | Panel | launch_testpanel.bat | 5010 |  |
| .venv\Lib\site-packages\hvplot\tests\testutil.py | Panel | launch_testutil.bat | 5010 |  |
| .venv\Lib\site-packages\hvplot\ui.py | Panel | launch_equity_curve_streamlit.bat | 5010 | Explore your data and design your plot via an interactive user interface. |
| .venv\Lib\site-packages\hvplot\util.py | Panel | launch_util.bat | 5010 |  |
| .venv\Lib\site-packages\hvplot\utilities.py | Panel | launch_utilities.bat | 5010 |  |
| .venv\Lib\site-packages\panel\__init__.py | Panel | launch___init__.bat | 5010 |  |
| .venv\Lib\site-packages\panel\config.py | Panel | launch_config.bat | 5010 |  |
| .venv\Lib\site-packages\panel\custom.py | Panel | launch_custom.bat | 5010 |  |
| .venv\Lib\site-packages\panel\io\__init__.py | Panel | launch___init__.bat | 5010 |  |
| .venv\Lib\site-packages\panel\io\application.py | Panel | launch_application.bat | 5010 |  |
| .venv\Lib\site-packages\panel\io\handlers.py | Panel | launch_handlers.bat | 5010 |  |
| .venv\Lib\site-packages\panel\io\notebook.py | Panel | launch_notebook.bat | 5010 |  |
| .venv\Lib\site-packages\panel\io\pyodide.py | Panel | launch_pyodide.bat | 5010 |  |
| .venv\Lib\site-packages\panel\io\resources.py | Panel | launch_resources.bat | 5010 |  |
| .venv\Lib\site-packages\panel\layout\base.py | Panel | launch_base.bat | 5010 |  |
| .venv\Lib\site-packages\panel\layout\flex.py | Panel | launch_flex.bat | 5010 |  |
| .venv\Lib\site-packages\panel\layout\float.py | Panel | launch_float.bat | 5010 |  |
| .venv\Lib\site-packages\panel\layout\grid.py | Panel | launch_grid.bat | 5010 |  |
| .venv\Lib\site-packages\panel\layout\swipe.py | Panel | launch_swipe.bat | 5010 |  |
| .venv\Lib\site-packages\panel\pane\vtk\vtk.py | Panel | launch_vtk.bat | 5010 |  |
| .venv\Lib\site-packages\panel\param.py | Panel | launch_param.bat | 5010 |  |
| .venv\Lib\site-packages\panel\reactive.py | Panel | launch_reactive.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\command\test_serve.py | Panel | launch_test_serve.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\conftest.py | Panel | launch_conftest.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\io\test_handlers.py | Panel | launch_test_handlers.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\layout\test_accordion.py | Panel | launch_test_accordion.bat | 5010 | Set up a accordion instance |
| .venv\Lib\site-packages\panel\tests\layout\test_tabs.py | Panel | launch_test_tabs.bat | 5010 | Set up a tabs instance |
| .venv\Lib\site-packages\panel\tests\pane\test_alert.py | Panel | launch_test_alert.bat | 5010 | In this module we test the functionality of the alerts |
| .venv\Lib\site-packages\panel\tests\pane\test_base.py | Panel | launch_test_base.bat | 5010 | Ensures internal code correctly detects |
| .venv\Lib\site-packages\panel\tests\pane\test_holoviews.py | Panel | launch_test_holoviews.bat | 5010 | Create pane |
| .venv\Lib\site-packages\panel\tests\pane\test_plot.py | Panel | launch_test_plot.bat | 5010 | Create pane |
| .venv\Lib\site-packages\panel\tests\pane\test_vega.py | Panel | launch_test_vega.bat | 5010 | Tests for Vega.export() method. |
| .venv\Lib\site-packages\panel\tests\test_depends.py | Panel | launch_test_depends.bat | 5010 | Emits a Param warning |
| .venv\Lib\site-packages\panel\tests\test_docs.py | Panel | launch_test_docs.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\test_imports.py | Panel | launch_test_imports.bat | 5010 | \ |
| .venv\Lib\site-packages\panel\tests\test_models.py | Panel | launch_test_models.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\ui\command\test_serve.py | Panel | launch_test_serve.bat | 5010 | Timeout to ensure websocket is initialized |
| .venv\Lib\site-packages\panel\tests\ui\io\app.py | Panel | launch_dash_app.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\ui\io\test_convert.py | Panel | launch_test_convert.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\ui\io\test_location.py | Panel | launch_test_location.bat | 5010 | Simple app to set url by widgets' values |
| .venv\Lib\site-packages\panel\tests\ui\io\test_reload.py | Panel | launch_test_reload.bat | 5010 | Write and close (on windows the file handle cannot be reopened for reading otherwise) |
| .venv\Lib\site-packages\panel\tests\ui\io\test_resources.py | Panel | launch_test_resources.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\ui\test_auth.py | Panel | launch_test_auth.bat | 5010 | Loading password page is slow |
| .venv\Lib\site-packages\panel\tests\ui\test_param.py | Panel | launch_test_param.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\ui\widgets\test_input.py | Panel | launch_test_input.bat | 5010 | 1st week |
| .venv\Lib\site-packages\panel\tests\ui\widgets\test_sliders.py | Panel | launch_test_sliders.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\util.py | Panel | launch_util.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\widgets\test_debugger.py | Panel | launch_test_debugger.bat | 5010 | This module contains tests of the Debugger |
| .venv\Lib\site-packages\panel\tests\widgets\test_select.py | Panel | launch_test_select.bat | 5010 | Instantiate with groups and options |
| .venv\Lib\site-packages\panel\tests\widgets\test_speech_to_text.py | Panel | launch_test_speech_to_text.bat | 5010 |  |
| .venv\Lib\site-packages\panel\tests\widgets\test_terminal.py | Panel | launch_test_terminal.bat | 5010 | This module contains tests of the Terminal |
| .venv\Lib\site-packages\panel\tests\widgets\test_text_to_speech.py | Panel | launch_test_text_to_speech.bat | 5010 | By Aesop |
| .venv\Lib\site-packages\panel\tests\widgets\test_tqdm.py | Panel | launch_test_tqdm.bat | 5010 | Tests of the Tqdm indicator |
| .venv\Lib\site-packages\panel\util\__init__.py | Panel | launch___init__.bat | 5010 |  |
| .venv\Lib\site-packages\panel\util\warnings.py | Panel | launch_warnings.bat | 5010 |  |
| .venv\Lib\site-packages\panel\viewable.py | Panel | launch_viewable.bat | 5010 |  |
| .venv\Lib\site-packages\panel\widgets\tables.py | Panel | launch_tables.bat | 5010 |  |
| crypto_quant_v16\run_autonomous_system.py | Panel | launch_run_autonomous_system.bat | 5010 | Historique pour affichage graphique |
| crypto_quant_v16\tests\test_quant_dashboard.py | Panel | launch_test_quant_dashboard.bat | 5010 | Should instantiate dashboard main objects |
| crypto_quant_v16\tests\test_quant_dashboard_v16.py | Panel | launch_test_quant_dashboard_v16.bat | 5010 | header, controls, tabs |
| crypto_quant_v16\tests\test_quant_dashboard_v26.py | Panel | launch_test_quant_dashboard_v26.bat | 5010 | Should instantiate without error |
| crypto_quant_v16\tests\test_quant_dashboard_v26_visual.py | Panel | launch_test_quant_dashboard_v26_visual.bat | 5010 | Configure headless Chrome |
| crypto_quant_v16\tests\test_quant_dashboard_v26_widgets.py | Panel | launch_test_quant_dashboard_v26_widgets.bat | 5010 | Test symbol select widget exists and can be set |
| crypto_quant_v16\ui\components.py | Panel | launch_components.bat | 5010 | Panel widget pour choisir dynamiquement les indicateurs à afficher sur le graphique principal. |
| crypto_quant_v16\ui\quant_dashboard.py | Panel | launch_quant_dashboard_v16.bat | 5010 |  |
| crypto_quant_v16\ui\quant_dashboard_v13.py | Panel | launch_quant_dashboard_v13.bat | 5010 | Cluster Status panel |
| crypto_quant_v16\ui\quant_dashboard_v26.py | Panel | launch_quant_dashboard_v26.bat | 5010 |  |
| my_trading_system\ui\dashboard_my_trading_panel.py | Panel | launch_dashboard_my_trading_panel.bat | 5010 |  |
| my_trading_system\ui\dashboard_panel.py | Panel | launch_dashboard_panel.bat | 5010 |  |
| my_trading_system\ui\panel_test_minimal.py | Panel | launch_panel_test_minimal.bat | 5010 | Hello Panel!\nSi tu vois ce message, Panel fonctionne.").servable() |
| quant-trading-system\dashboard\panel_overview.py | Panel | launch_panel_overview.bat | 5010 |  |
| quant_hedge_ai\dashboard\quant_terminal_v12.py | Panel | launch_quant_terminal_v12.bat | 5010 |  |
| results\dashboard_evolution_results.py | Panel | launch_dashboard_evolution_results.bat | 5010 | Tabs for each world |
| results\dashboard_panel.py | Panel | launch_dashboard_panel.bat | 5010 | Tabs for each world |
| scripts\crypto_market_scanner.py | Panel | launch_crypto_market_scanner.bat | 5010 | cryptos à scanner |
| scripts\crypto_terminal.py | Panel | launch_crypto_terminal.bat | 5010 | connexion Binance |
| scripts\test_panel.py | Panel | launch_test_panel.bat | 5010 | Créer un dossier dans data/ |
| scripts\test_python.py | Panel | launch_test_python.bat | 5010 | Créer un dossier dans data/ |
| .venv\Lib\site-packages\annotated_text\__init__.py | Streamlit | launch___init__.bat | 8501 | Writes text with annotations into your Streamlit app. |
| .venv\Lib\site-packages\camera_input_live\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\markdownlit\__init__.py | Streamlit | launch___init__.bat | 8501 | Apply custom CSS in a Streamlit app. |
| .venv\Lib\site-packages\markdownlit\extensions\at_sign.py | Streamlit | launch_at_sign.bat | 8501 | Transforms '@(icon)(label)(url)' into HTML. |
| .venv\Lib\site-packages\st_keyup\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\__init__.py | Streamlit | launch___init__.bat | 8501 | Streamlit. |
| .venv\Lib\site-packages\streamlit\commands\echo.py | Streamlit | launch_echo.bat | 8501 | Use in a `with` block to draw some code on the app, then execute it. |
| .venv\Lib\site-packages\streamlit\commands\execution_control.py | Streamlit | launch_execution_control.bat | 8501 | Stops execution immediately. |
| .venv\Lib\site-packages\streamlit\commands\logo.py | Streamlit | launch_logo.bat | 8501 | Handle App logos. |
| .venv\Lib\site-packages\streamlit\commands\navigation.py | Streamlit | launch_navigation.bat | 8501 | Convert various input types to StreamlitPage objects. |
| .venv\Lib\site-packages\streamlit\commands\page_config.py | Streamlit | launch_page_config.bat | 8501 | Return the string to pass to the frontend to have it show |
| .venv\Lib\site-packages\streamlit\components\v1\__init__.py | Streamlit | launch___init__.bat | 8501 | Contains the files and modules for the exposed API. |
| .venv\Lib\site-packages\streamlit\components\v2\__init__.py | Streamlit | launch___init__.bat | 8501 | Register the st.components.v2 API namespace. |
| .venv\Lib\site-packages\streamlit\components\v2\types.py | Streamlit | launch_types.bat | 8501 | Shared typing utilities for the `st.components.v2` API. |
| .venv\Lib\site-packages\streamlit\config.py | Streamlit | launch_config.bat | 8501 | Loads the configuration data. |
| .venv\Lib\site-packages\streamlit\connections\base_connection.py | Streamlit | launch_base_connection.bat | 8501 | The abstract base class that all Streamlit Connections must inherit from. |
| .venv\Lib\site-packages\streamlit\connections\snowflake_connection.py | Streamlit | launch_snowflake_connection.bat | 8501 | Base class for Snowflake connections. |
| .venv\Lib\site-packages\streamlit\connections\snowpark_connection.py | Streamlit | launch_snowpark_connection.bat | 8501 | A connection to Snowpark using snowflake.snowpark.session.Session. Initialize using |
| .venv\Lib\site-packages\streamlit\connections\sql_connection.py | Streamlit | launch_sql_connection.bat | 8501 | A connection to a SQL database using a SQLAlchemy Engine. |
| .venv\Lib\site-packages\streamlit\delta_generator.py | Streamlit | launch_delta_generator.bat | 8501 | Allows us to create and absorb changes (aka Deltas) to elements. |
| .venv\Lib\site-packages\streamlit\deprecation_util.py | Streamlit | launch_deprecation_util.bat | 8501 | True if we should print deprecation warnings to the browser. |
| .venv\Lib\site-packages\streamlit\elements\alert.py | Streamlit | launch_alert_dashboard.bat | 8501 | Display error message. |
| .venv\Lib\site-packages\streamlit\elements\arrow.py | Streamlit | launch_arrow.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\elements\balloons.py | Streamlit | launch_balloons.bat | 8501 | Draw celebratory balloons. |
| .venv\Lib\site-packages\streamlit\elements\code.py | Streamlit | launch_code.bat | 8501 | Display a code block with optional syntax highlighting. |
| .venv\Lib\site-packages\streamlit\elements\deck_gl_json_chart.py | Streamlit | launch_deck_gl_json_chart.bat | 8501 | Parse and check the user provided selection modes. |
| .venv\Lib\site-packages\streamlit\elements\dialog_decorator.py | Streamlit | launch_dialog_decorator.bat | 8501 | Check the current stack for existing DeltaGenerator's of type 'dialog'. |
| .venv\Lib\site-packages\streamlit\elements\empty.py | Streamlit | launch_empty.bat | 8501 | Insert a single-element container. |
| .venv\Lib\site-packages\streamlit\elements\exception.py | Streamlit | launch_exception.bat | 8501 | Display an exception. |
| .venv\Lib\site-packages\streamlit\elements\form.py | Streamlit | launch_form.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\elements\graphviz_chart.py | Streamlit | launch_graphviz_chart.bat | 8501 | Streamlit support for GraphViz charts. |
| .venv\Lib\site-packages\streamlit\elements\heading.py | Streamlit | launch_heading.bat | 8501 | Display text in header formatting. |
| .venv\Lib\site-packages\streamlit\elements\help.py | Streamlit | launch_help.bat | 8501 | Allows us to create and absorb changes (aka Deltas) to elements. |
| .venv\Lib\site-packages\streamlit\elements\html.py | Streamlit | launch_html.bat | 8501 | Insert HTML into your app. |
| .venv\Lib\site-packages\streamlit\elements\iframe.py | Streamlit | launch_iframe.bat | 8501 | Load a remote URL in an iframe. |
| .venv\Lib\site-packages\streamlit\elements\image.py | Streamlit | launch_image.bat | 8501 | Image marshalling. |
| .venv\Lib\site-packages\streamlit\elements\json.py | Streamlit | launch_json.bat | 8501 | A repr function for json.dumps default arg, which tries to serialize sets |
| .venv\Lib\site-packages\streamlit\elements\layouts.py | Streamlit | launch_layouts.bat | 8501 | Serializer/deserializer for expander widget state. |
| .venv\Lib\site-packages\streamlit\elements\lib\column_types.py | Streamlit | launch_column_types.bat | 8501 | Validate a color for a chart column. |
| .venv\Lib\site-packages\streamlit\elements\lib\mutable_expander_container.py | Streamlit | launch_mutable_expander_container.bat | 8501 | A container returned by ``st.expander``. |
| .venv\Lib\site-packages\streamlit\elements\lib\mutable_popover_container.py | Streamlit | launch_mutable_popover_container.bat | 8501 | A container returned by ``st.popover``. |
| .venv\Lib\site-packages\streamlit\elements\lib\mutable_tab_container.py | Streamlit | launch_mutable_tab_container.bat | 8501 | A container returned for each tab in ``st.tabs``. |
| .venv\Lib\site-packages\streamlit\elements\map.py | Streamlit | launch_map.bat | 8501 | A wrapper for simple PyDeck scatter charts. |
| .venv\Lib\site-packages\streamlit\elements\markdown.py | Streamlit | launch_markdown.bat | 8501 | Display string formatted as Markdown. |
| .venv\Lib\site-packages\streamlit\elements\media.py | Streamlit | launch_media.bat | 8501 | Display an audio player. |
| .venv\Lib\site-packages\streamlit\elements\metric.py | Streamlit | launch_metric.bat | 8501 | Display a metric in big bold font, with an optional indicator of how the metric changed. |
| .venv\Lib\site-packages\streamlit\elements\pdf.py | Streamlit | launch_pdf.bat | 8501 | Get the PDF custom component if available. |
| .venv\Lib\site-packages\streamlit\elements\plotly_chart.py | Streamlit | launch_plotly_chart.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\elements\progress.py | Streamlit | launch_progress.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\elements\pyplot.py | Streamlit | launch_pyplot.bat | 8501 | Streamlit support for Matplotlib PyPlot charts. |
| .venv\Lib\site-packages\streamlit\elements\snow.py | Streamlit | launch_snow.bat | 8501 | Draw celebratory snowfall. |
| .venv\Lib\site-packages\streamlit\elements\space.py | Streamlit | launch_space.bat | 8501 | Add vertical or horizontal space. |
| .venv\Lib\site-packages\streamlit\elements\spinner.py | Streamlit | launch_spinner.bat | 8501 | Display a loading spinner while executing a block of code. |
| .venv\Lib\site-packages\streamlit\elements\table.py | Streamlit | launch_table.bat | 8501 | Parse and check the user provided border mode. |
| .venv\Lib\site-packages\streamlit\elements\text.py | Streamlit | launch_text.bat | 8501 | Write text without Markdown or HTML parsing. |
| .venv\Lib\site-packages\streamlit\elements\toast.py | Streamlit | launch_toast.bat | 8501 | Display a short message, known as a notification "toast". |
| .venv\Lib\site-packages\streamlit\elements\vega_charts.py | Streamlit | launch_vega_charts.bat | 8501 | Collection of chart commands that are rendered via our vega-lite chart component. |
| .venv\Lib\site-packages\streamlit\elements\widgets\audio_input.py | Streamlit | launch_audio_input.bat | 8501 | Display a widget that returns an audio recording from the user's microphone. |
| .venv\Lib\site-packages\streamlit\elements\widgets\button.py | Streamlit | launch_button.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\elements\widgets\button_group.py | Streamlit | launch_button_group.bat | 8501 | String-based serde for single-select ButtonGroup widgets. |
| .venv\Lib\site-packages\streamlit\elements\widgets\camera_input.py | Streamlit | launch_camera_input.bat | 8501 | Display a widget that returns pictures from the user's webcam. |
| .venv\Lib\site-packages\streamlit\elements\widgets\chat.py | Streamlit | launch_chat.bat | 8501 | Represents the value returned by `st.chat_input` after user interaction. |
| .venv\Lib\site-packages\streamlit\elements\widgets\checkbox.py | Streamlit | launch_checkbox.bat | 8501 | Display a checkbox widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\color_picker.py | Streamlit | launch_color_picker.bat | 8501 | Normalize a hex color to include the # prefix. |
| .venv\Lib\site-packages\streamlit\elements\widgets\data_editor.py | Streamlit | launch_data_editor.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\elements\widgets\feedback.py | Streamlit | launch_feedback_dashboard.bat | 8501 | Get the number of options for the given feedback type. |
| .venv\Lib\site-packages\streamlit\elements\widgets\file_uploader.py | Streamlit | launch_file_uploader.bat | 8501 | Display a file uploader widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\multiselect.py | Streamlit | launch_multiselect.bat | 8501 | Initialize the MultiSelectSerde. |
| .venv\Lib\site-packages\streamlit\elements\widgets\number_input.py | Streamlit | launch_number_input.bat | 8501 | Display a numeric input widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\radio.py | Streamlit | launch_radio.bat | 8501 | Serializer/deserializer for Radio widget values. |
| .venv\Lib\site-packages\streamlit\elements\widgets\select_slider.py | Streamlit | launch_select_slider.bat | 8501 | Serializer/deserializer for select_slider widget values. |
| .venv\Lib\site-packages\streamlit\elements\widgets\selectbox.py | Streamlit | launch_selectbox.bat | 8501 | Initialize the SelectboxSerde. |
| .venv\Lib\site-packages\streamlit\elements\widgets\slider.py | Streamlit | launch_slider.bat | 8501 | Restore times/datetimes to original timezone (dates are always naive). |
| .venv\Lib\site-packages\streamlit\elements\widgets\text_widgets.py | Streamlit | launch_text_widgets.bat | 8501 | Display a single-line text input widget. |
| .venv\Lib\site-packages\streamlit\elements\widgets\time_widgets.py | Streamlit | launch_time_widgets.bat | 8501 | Return a time without seconds, microseconds, or timezone info. |
| .venv\Lib\site-packages\streamlit\elements\write.py | Streamlit | launch_write.bat | 8501 | Stream a generator, iterable, or stream-like sequence to the app. |
| .venv\Lib\site-packages\streamlit\error_util.py | Streamlit | launch_error_util.bat | 8501 | Show the exception on the frontend. |
| .venv\Lib\site-packages\streamlit\hello\animation_demo.py | Streamlit | launch_animation_demo.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\hello\dataframe_demo.py | Streamlit | launch_dataframe_demo.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\hello\hello.py | Streamlit | launch_hello.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\hello\mapping_demo.py | Streamlit | launch_mapping_demo.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\hello\plotting_demo.py | Streamlit | launch_plotting_demo.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\hello\streamlit_app.py | Streamlit | launch_streamlit_app.bat | 8501 | Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022-2026) |
| .venv\Lib\site-packages\streamlit\hello\utils.py | Streamlit | launch_utils.bat | 8501 | Showing the code of the demo. |
| .venv\Lib\site-packages\streamlit\navigation\page.py | Streamlit | launch_page.bat | 8501 | Configure a page for ``st.navigation`` in a multipage app. |
| .venv\Lib\site-packages\streamlit\runtime\app_session.py | Streamlit | launch_app_session.bat | 8501 | Randomly generate a unique ID for a script execution. |
| .venv\Lib\site-packages\streamlit\runtime\caching\cache_data_api.py | Streamlit | launch_cache_data_api.bat | 8501 | @st.cache_data: pickle-based caching. |
| .venv\Lib\site-packages\streamlit\runtime\caching\cache_resource_api.py | Streamlit | launch_cache_resource_api.bat | 8501 | @st.cache_resource implementation. |
| .venv\Lib\site-packages\streamlit\runtime\caching\cache_utils.py | Streamlit | launch_cache_utils.bat | 8501 | Common cache logic shared by st.cache_data and st.cache_resource. |
| .venv\Lib\site-packages\streamlit\runtime\caching\cached_message_replay.py | Streamlit | launch_cached_message_replay.bat | 8501 | An element's message and related metadata for |
| .venv\Lib\site-packages\streamlit\runtime\caching\legacy_cache_api.py | Streamlit | launch_legacy_cache_api.bat | 8501 | A library of caching utilities. |
| .venv\Lib\site-packages\streamlit\runtime\connection_factory.py | Streamlit | launch_connection_factory.bat | 8501 | Create an instance of connection_class with the given name and kwargs. |
| .venv\Lib\site-packages\streamlit\runtime\context.py | Streamlit | launch_context.bat | 8501 | Get the ClientContext for the current session. |
| .venv\Lib\site-packages\streamlit\runtime\fragment.py | Streamlit | launch_fragment.bat | 8501 | A key-value store for Fragments. Used to implement the @st.fragment decorator. |
| .venv\Lib\site-packages\streamlit\runtime\scriptrunner\magic.py | Streamlit | launch_magic.bat | 8501 | Modifies the code to support magic Streamlit commands. |
| .venv\Lib\site-packages\streamlit\runtime\scriptrunner\magic_funcs.py | Streamlit | launch_magic_funcs.bat | 8501 | The function that gets magic-ified into Streamlit apps. |
| .venv\Lib\site-packages\streamlit\runtime\secrets.py | Streamlit | launch_secrets.bat | 8501 | SecretErrorMessages stores all error messages we use for secrets to allow customization |
| .venv\Lib\site-packages\streamlit\runtime\state\query_params_proxy.py | Streamlit | launch_query_params_proxy.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\testing\v1\app_test.py | Streamlit | launch_app_test.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit\user_info.py | Streamlit | launch_user_info.bat | 8501 | Initiate the login flow for the given provider. |
| .venv\Lib\site-packages\streamlit\web\cli.py | Streamlit | launch_cli.bat | 8501 | A script which is run when the Streamlit package is executed. |
| .venv\Lib\site-packages\streamlit\web\server\app_discovery.py | Streamlit | launch_app_discovery.bat | 8501 | App discovery utilities for detecting ASGI app instances in scripts. |
| .venv\Lib\site-packages\streamlit\web\server\bidi_component_request_handler.py | Streamlit | launch_bidi_component_request_handler.bat | 8501 | Serve static assets for Custom Components v2. |
| .venv\Lib\site-packages\streamlit\web\server\component_request_handler.py | Streamlit | launch_component_request_handler.bat | 8501 | Disable cache for HTML files. |
| .venv\Lib\site-packages\streamlit\web\server\server.py | Streamlit | launch_server.bat | 8501 | Get the websocket ping interval and timeout from config or defaults. |
| .venv\Lib\site-packages\streamlit_avatar\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_card\__init__.py | Streamlit | launch___init__.bat | 8501 | Creates a UI card like component. |
| .venv\Lib\site-packages\streamlit_embedcode\__init__.py | Streamlit | launch___init__.bat | 8501 | Strip trailing slash if present on link. |
| .venv\Lib\site-packages\streamlit_extras\add_vertical_space\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\altex\__init__.py | Streamlit | launch___init__.bat | 8501 | Collects a CSV/JSON file from a URL and load it into a dataframe, with appropriate caching (memo) |
| .venv\Lib\site-packages\streamlit_extras\app_logo\__init__.py | Streamlit | launch___init__.bat | 8501 | Add a logo (from logo_url) on the top of the navigation page of a multipage app. |
| .venv\Lib\site-packages\streamlit_extras\badges\__init__.py | Streamlit | launch___init__.bat | 8501 | Easily create a visual badge for PyPI, GitHub, Streamlit Cloud or other social platforms. |
| .venv\Lib\site-packages\streamlit_extras\bottom_container\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\button_selector\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\buy_me_a_coffee\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\camera_input_live\__init__.py | Streamlit | launch___init__.bat | 8501 | See a new image every second") |
| .venv\Lib\site-packages\streamlit_extras\capture\__init__.py | Streamlit | launch___init__.bat | 8501 | Redirect STDOUT and STDERR to streamlit functions. |
| .venv\Lib\site-packages\streamlit_extras\chart_annotations\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\chart_container\__init__.py | Streamlit | launch___init__.bat | 8501 | Embed chart in a (chart, data, export, explore) tabs container to let the viewer explore and export its underlying data. |
| .venv\Lib\site-packages\streamlit_extras\colored_header\__init__.py | Streamlit | launch___init__.bat | 8501 | Add colorful headers to your Streamlit app. |
| .venv\Lib\site-packages\streamlit_extras\concurrency_limiter\__init__.py | Streamlit | launch___init__.bat | 8501 | Add concurrency_limiter decorator to your Streamlit app. |
| .venv\Lib\site-packages\streamlit_extras\customize_running\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\dataframe_explorer\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\echo_expander\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\floating_button\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\function_explorer\__init__.py | Streamlit | launch___init__.bat | 8501 | Gives a Streamlit UI to any function. |
| .venv\Lib\site-packages\streamlit_extras\great_tables\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\grid\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\image_coordinates\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\image_in_tables\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\image_selector\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\keyboard_text\__init__.py | Streamlit | launch___init__.bat | 8501 | <style> |
| .venv\Lib\site-packages\streamlit_extras\keyboard_url\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\let_it_rain\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\mandatory_date_range\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\markdownlit\__init__.py | Streamlit | launch___init__.bat | 8501 | mdlit("{code}") |
| .venv\Lib\site-packages\streamlit_extras\mention\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\metric_cards\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\no_default_selectbox\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\pdf_viewer\__init__.py | Streamlit | launch___init__.bat | 8501 | Display a PDF document. |
| .venv\Lib\site-packages\streamlit_extras\prometheus\__init__.py | Streamlit | launch___init__.bat | 8501 | Custom OpenMetrics collected via protobuf is not currently supported. |
| .venv\Lib\site-packages\streamlit_extras\prometheus\example\app.py | Streamlit | launch_dash_app.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\prometheus\example\metrics.py | Streamlit | launch_metrics.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\row\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\sandbox\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\skeleton\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\st_keyup\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\star_rating\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\stateful_button\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\stateful_chat\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\stodo\__init__.py | Streamlit | launch___init__.bat | 8501 | Create a to_do item |
| .venv\Lib\site-packages\streamlit_extras\stoggle\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\streaming_write\__init__.py | Streamlit | launch___init__.bat | 8501 | Drop-in replacement for `st.write` with streaming support. |
| .venv\Lib\site-packages\streamlit_extras\stylable_container\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\switch_page_button\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\tags\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\theme\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\toggle_switch\__init__.py | Streamlit | launch___init__.bat | 8501 | On/Off Toggle Switch with color customizations. |
| .venv\Lib\site-packages\streamlit_extras\vertical_slider\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_extras\word_importances\__init__.py | Streamlit | launch___init__.bat | 8501 | Adds a background color to each word based on its importance (float from -1 to 1) |
| .venv\Lib\site-packages\streamlit_faker\chart.py | Streamlit | launch_chart.bat | 8501 | Collects a CSV/JSON file from a URL and load it into a dataframe, with appropriate caching (memo) |
| .venv\Lib\site-packages\streamlit_faker\data_display.py | Streamlit | launch_data_display.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_faker\input.py | Streamlit | launch_input.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_faker\media.py | Streamlit | launch_media.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_faker\status.py | Streamlit | launch_status.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_faker\text.py | Streamlit | launch_text.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_image_coordinates\__init__.py | Streamlit | launch___init__.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_theme\__init__.py | Streamlit | launch___init__.bat | 8501 | Show the installed version of the Streamlit Theme package. |
| .venv\Lib\site-packages\streamlit_theme\example.py | Streamlit | launch_example.bat | 8501 |  |
| .venv\Lib\site-packages\streamlit_toggle\__init__.py | Streamlit | launch___init__.bat | 8501 | D3D3D3', active_color=" |
| .venv\Lib\site-packages\streamlit_vertical_slider\__init__.py | Streamlit | launch___init__.bat | 8501 | E5E9F1", |
| ONBOARDING_SCRIPT.py | Streamlit | launch_ONBOARDING_SCRIPT.bat | 8501 |  |
| ai_autonomous_loop\feedback_dashboard.py | Streamlit | launch_feedback_dashboard.bat | 8501 | Historique rapide |
| bot-v3\interface\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 | Add parent directory to path |
| crypto_quant_v16\supervision\dashboard_web.py | Streamlit | launch_dashboard_web.bat | 8501 | Exécution autonome pour test rapide |
| dashboard\alert_dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 |  |
| evolution_3d_view.py | Streamlit | launch_evolution_3d_view.bat | 8501 | noqa: F401 |
| evolution_dashboard.py | Streamlit | launch_evolution_dashboard.bat | 8501 |  |
| quant-ai-system\dashboard\streamlit_dashboard.py | Streamlit | launch_streamlit_dashboard.bat | 8501 |  |
| quant-bot-v3-pro\dashboard\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 | Add parent to path |
| quant-hedge-bot\dashboard\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 |  |
| quant-hedge-bot\professional_dashboard.py | Streamlit | launch_professional_dashboard.bat | 8501 |  |
| quant-trading-system\dashboard\dashboard.py | Streamlit | launch_alert_dashboard.bat | 8501 |  |
| results\equity_curve_streamlit.py | Streamlit | launch_equity_curve_streamlit.bat | 8501 | Charger le dernier CSV d'equity curves |
| scripts\generate_dashboards_table.py | Streamlit | launch_generate_dashboards_table.bat | 8501 | (.*?) |
| supervision\botdoctor_dashboard.py | Streamlit | launch_botdoctor_dashboard.bat | 8501 | Chargement des données |
| supervision\dashboard_advanced.py | Streamlit | launch_dashboard_advanced.bat | 8501 | Chargement des données |

--------------------------------|-------------|------------------------------------|-----------------|----------------------------------------------------|
| alert_dashboard.py             | Streamlit   | launch_alert_dashboard.bat         | 8501            | Supervision intelligente & auto-heal               |
| feedback_dashboard.py          | Streamlit   | launch_feedback_dashboard.bat      | 8501            | Feedback R&D boucle autonome                       |
| dashboard_advanced.py          | Streamlit   | launch_dashboard_advanced.bat      | 8501            | BotDoctor Dashboard avancé                         |
| botdoctor_dashboard.py         | Streamlit   | launch_botdoctor_dashboard.bat     | 8501            | BotDoctor supervision synthétique                  |
| equity_curve_streamlit.py      | Streamlit   | launch_equity_curve_streamlit.bat  | 8501            | Visualisation courbe equity                        |
| evolution_dashboard.py         | Streamlit   | launch_evolution_dashboard.bat     | 8501            | Dashboard évolution multi-monde                    |
| evolution_3d_view.py           | Streamlit   | launch_evolution_3d_view.bat       | 8501            | Visualisation 3D évolution                         |
| quant_terminal_v12.py          | Panel       | launch_quant_terminal_v12.bat      | 5010            | Quant Terminal V12 (Panel + Plotly)                |
| dashboard_quant_terminal.py    | Panel       | launch_dashboard_quant_terminal.bat| 5011            | Quant Terminal V12 (Panel, version alternative)    |
| quant_dashboard.py (V16)       | Panel       | launch_quant_dashboard_v16.bat     | 5012            | Dashboard crypto_quant_v16 (Panel)                 |
| panel_overview.py              | Panel       | launch_panel_overview.bat          | 5013            | Panel Overview Dashboard (quant-trading-system)    |
| dash_app.py                    | Dash        | launch_dash_app.bat                | 8050            | Dashboard Dash (quant-trading-system)              |
| dashboard_fastapi.py              | FastAPI      | launch_dashboard_fastapi.bat      | 8080            | Dashboard FastAPI (my_trading_system)              |
| monitoring_api.py                 | FastAPI      | launch_monitoring_api.bat         | 8081            | API Monitoring FastAPI (supervision)               |
| botdoctor_api.py                  | FastAPI      | launch_botdoctor_api.bat          | 8082            | API BotDoctor FastAPI (supervision)                |
| api_rest.py                       | FastAPI      | launch_api_rest.bat               | 8083            | API REST BotDoctor FastAPI (supervision)           |
| dashboard_api.py                  | FastAPI      | launch_dashboard_api.bat          | 8084            | API Dashboard FastAPI (crypto_quant_v16)           |

## Utilisation

- Double-cliquez sur le script `.bat` correspondant ou lancez-le depuis PowerShell.
- Pour Panel/Dash, le port par défaut est indiqué (modifiez-le si besoin pour éviter les collisions).
- Les dashboards sont exclus des tests automatiques pour éviter les faux positifs lors des CI/tests unitaires.

## Ajout d’un nouveau dashboard
- Placez le script dans le dossier approprié.
- Ajoutez le bloc d’exclusion pytest (voir exemples ci-dessus).
- Créez un script `.bat` de lancement similaire.
- Ajoutez une ligne dans ce tableau.

---

Pour toute question ou ajout, contactez l’équipe dev ou consultez la documentation technique du dépôt.
