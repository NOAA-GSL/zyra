from typing import Optional
import argparse
import sys


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="datavizhub")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Pre-scan argv to support lazy registration and avoid importing heavy stacks unnecessarily
    args_list = argv if argv is not None else sys.argv[1:]
    first_non_flag = next((a for a in args_list if not a.startswith("-")), None)

    # Always make 'run' available (lightweight)
    from datavizhub.pipeline_runner import register_cli_run as _register_run
    _register_run(sub)

    # Lazy-register only the requested top-level group when possible
    if first_non_flag == "acquire":
        from datavizhub.connectors import ingest as _ingest_mod

        p_acq = sub.add_parser("acquire", help="Acquire/ingest data from sources")
        acq_sub = p_acq.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(acq_sub)
    elif first_non_flag == "process":
        from datavizhub import processing as _process_mod

        p_proc = sub.add_parser("process", help="Processing commands (GRIB/NetCDF/GeoTIFF)")
        proc_sub = p_proc.add_subparsers(dest="process_cmd", required=True)
        _process_mod.register_cli(proc_sub)
    elif first_non_flag == "visualize":
        from datavizhub import visualization as _visual_mod

        p_viz = sub.add_parser("visualize", help="Visualization commands (static/interactive/animation)")
        viz_sub = p_viz.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(viz_sub)
    elif first_non_flag == "decimate":
        from datavizhub.connectors import egress as _egress_mod

        p_decimate = sub.add_parser("decimate", help="Write/egress data to destinations")
        dec_sub = p_decimate.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(dec_sub)
    elif first_non_flag == "run":
        # Already registered above
        pass
    else:
        # Fallback: register the full CLI tree when we cannot infer the target
        from datavizhub.connectors import ingest as _ingest_mod
        from datavizhub.connectors import egress as _egress_mod
        from datavizhub import processing as _process_mod
        from datavizhub import visualization as _visual_mod

        p_acq = sub.add_parser("acquire", help="Acquire/ingest data from sources")
        acq_sub = p_acq.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(acq_sub)

        p_proc = sub.add_parser("process", help="Processing commands (GRIB/NetCDF/GeoTIFF)")
        proc_sub = p_proc.add_subparsers(dest="process_cmd", required=True)
        _process_mod.register_cli(proc_sub)

        p_viz = sub.add_parser("visualize", help="Visualization commands (static/interactive/animation)")
        viz_sub = p_viz.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(viz_sub)

        p_decimate = sub.add_parser("decimate", help="Write/egress data to destinations")
        dec_sub = p_decimate.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(dec_sub)

    args = parser.parse_args(args_list)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
