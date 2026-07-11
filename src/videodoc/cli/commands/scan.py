import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.core.errors import InvalidConfigError, ProjectNotFoundError
from videodoc.core.services.project_service import ProjectService
from videodoc.core.services.scan_service import SourcePathReport, SourceScanService


def scan_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        result = SourceScanService(service.project_dir, service.config).run()
    except (ProjectNotFoundError, InvalidConfigError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")

    def _suffix(report: SourcePathReport) -> str:
        return f" (external: {report.resolved_path})" if report.is_external else ""

    cb = result.manifest.codebase
    label = f"present ({len(cb.files)} files)" if cb.present else "not present"

    render_summary_table([
        ("Videos", f"{len(result.manifest.videos)} found{_suffix(result.videos_report)}"),
        ("Attachments", f"{len(result.manifest.attachments)} found{_suffix(result.attachments_report)}"),
        ("Codebase", f"{label}{_suffix(result.codebase_report)}"),
    ])

    for name, report in (
        ("videos", result.videos_report),
        ("attachments", result.attachments_report),
        ("codebase", result.codebase_report),
    ):
        # Every external source is checked, not just videos: attachments and
        # codebase pointing at a missing external path are just as real.
        if report.is_external and not report.is_directory:
            if report.exists:
                print_warning(f"external {name} path exists but is not a directory: {report.resolved_path}")
            else:
                print_warning(f"external {name} path not found: {report.resolved_path}")

    for scan_error in result.manifest.scan_errors:
        print_warning(scan_error)

    excl = result.manifest.exclusions
    console.print(f"Excluded directories: {', '.join(excl.directories) or '(none)'}")
    console.print(f"Excluded file patterns: {', '.join(excl.file_patterns) or '(none)'}")
    console.print(f"Sources manifest updated: {result.manifest_path.name}")
