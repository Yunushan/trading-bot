from __future__ import annotations

from types import SimpleNamespace


def _load_binding_modules() -> SimpleNamespace:
    from app.desktop import create_desktop_service_client
    from app.desktop import service_bridge as desktop_service_bridge
    from app.gui.backtest import (
        bridge_runtime,
        execution_runtime,
        results_runtime,
        state_runtime,
        tab_runtime,
        template_runtime,
    )
    from app.gui.chart import (
        display_runtime,
        host_runtime,
        selection_runtime,
        tab_runtime as chart_tab_runtime,
        view_runtime,
    )
    from app.gui.code import runtime as code_runtime, tab_runtime as code_tab_runtime
    from app.gui.dashboard import (
        actions_runtime,
        chart_runtime,
        header_runtime,
        indicator_runtime,
        log_runtime,
        markets_runtime,
        state_runtime as dashboard_state_runtime,
        strategy_runtime,
    )
    from app.gui.positions import positions_runtime, tab_runtime as positions_tab_runtime
    from app.gui.runtime.account import (
        account_runtime,
        balance_runtime,
        margin_runtime,
    )
    from app.gui.runtime.service import (
        service_api_runtime,
        session_runtime,
        status_runtime,
    )
    from app.gui.runtime.strategy import (
        context_runtime,
        control_runtime,
        controls_runtime,
        indicator_runtime as strategy_indicator_runtime,
        override_runtime,
        stop_loss_runtime,
        ui_runtime as strategy_ui_runtime,
    )
    from app.gui.runtime.ui import (
        secondary_tabs_runtime,
        tab_runtime as runtime_tab_runtime,
        theme_runtime,
        ui_misc_runtime,
    )
    from app.gui.runtime.window import (
        bootstrap_runtime,
        init_finalize_runtime,
        runtime as window_runtime,
    )
    from app.gui.shared import config_runtime
    from app.gui.trade import trade_runtime

    return SimpleNamespace(
        desktop=SimpleNamespace(
            create_service_client=create_desktop_service_client,
            service_bridge=desktop_service_bridge,
        ),
        backtest=SimpleNamespace(
            bridge=bridge_runtime,
            execution=execution_runtime,
            results=results_runtime,
            state=state_runtime,
            tab=tab_runtime,
            template=template_runtime,
        ),
        chart=SimpleNamespace(
            display=display_runtime,
            host=host_runtime,
            selection=selection_runtime,
            tab=chart_tab_runtime,
            view=view_runtime,
        ),
        code=SimpleNamespace(
            runtime=code_runtime,
            tab=code_tab_runtime,
        ),
        dashboard=SimpleNamespace(
            actions=actions_runtime,
            chart=chart_runtime,
            header=header_runtime,
            indicator=indicator_runtime,
            log=log_runtime,
            markets=markets_runtime,
            state=dashboard_state_runtime,
            strategy=strategy_runtime,
        ),
        positions=SimpleNamespace(
            runtime=positions_runtime,
            tab=positions_tab_runtime,
        ),
        runtime=SimpleNamespace(
            account=SimpleNamespace(
                account=account_runtime,
                balance=balance_runtime,
                margin=margin_runtime,
            ),
            service=SimpleNamespace(
                api=service_api_runtime,
                session=session_runtime,
                status=status_runtime,
            ),
            strategy=SimpleNamespace(
                context=context_runtime,
                control=control_runtime,
                controls=controls_runtime,
                indicator=strategy_indicator_runtime,
                override=override_runtime,
                stop_loss=stop_loss_runtime,
                ui=strategy_ui_runtime,
            ),
            ui=SimpleNamespace(
                secondary_tabs=secondary_tabs_runtime,
                tab=runtime_tab_runtime,
                theme=theme_runtime,
                ui_misc=ui_misc_runtime,
            ),
            window=SimpleNamespace(
                bootstrap=bootstrap_runtime,
                init_finalize=init_finalize_runtime,
                runtime=window_runtime,
            ),
        ),
        shared=SimpleNamespace(config=config_runtime),
        trade=SimpleNamespace(runtime=trade_runtime),
    )
