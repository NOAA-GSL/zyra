from typing import Optional
import argparse
import sys


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="datavizhub")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Pre-scan argv to support lazy registration and avoid heavy imports when running 'run'
    args_list = argv if argv is not None else sys.argv[1:]
    first_non_flag = next((a for a in args_list if not a.startswith("-")), None)

    if first_non_flag == "run":
        # Register only the lightweight pipeline runner
        from datavizhub.pipeline_runner import register_cli_run as _register_run

        _register_run(sub)
    else:
        # Register full CLI tree (may import optional heavy deps)
        from datavizhub.connectors import ingest as _ingest_mod
        from datavizhub.connectors import egress as _egress_mod
        from datavizhub.pipeline_runner import register_cli_run as _register_run
        from datavizhub import processing as _process_mod
        from datavizhub import visualization as _visual_mod

        # acquire
        p_acq = sub.add_parser("acquire", help="Acquire/ingest data from sources")
        acq_sub = p_acq.add_subparsers(dest="acquire_cmd", required=True)
        _ingest_mod.register_cli(acq_sub)

        # process
        p_proc = sub.add_parser("process", help="Processing commands (GRIB/NetCDF/GeoTIFF)")
        proc_sub = p_proc.add_subparsers(dest="process_cmd", required=True)
        _process_mod.register_cli(proc_sub)

        # visualize
        p_viz = sub.add_parser("visualize", help="Visualization commands (static/interactive/animation)")
        viz_sub = p_viz.add_subparsers(dest="visualize_cmd", required=True)
        _visual_mod.register_cli(viz_sub)

        # decimate (egress)
        p_decimate = sub.add_parser("decimate", help="Write/egress data to destinations")
        dec_sub = p_decimate.add_subparsers(dest="decimate_cmd", required=True)
        _egress_mod.register_cli(dec_sub)

        # run
        _register_run(sub)

    args = parser.parse_args(args_list)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
