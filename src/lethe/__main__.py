import os
import sys
import tempfile
import textwrap
from itertools import groupby
from operator import attrgetter
from pathlib import Path
import json
import rich
import typer
import uuid7
from loguru import logger
from rich.console import Console
from rich.table import Table
from stdnum import luhn
from typing_extensions import Annotated

from .dcm_deidentify import run_ctp
from .bscan_hashing import hash_BS_id
from .defaults import (
    DEFAULT_CPU_THREADS,
    DEFAULT_IGNORE_CSV_PREFIX,
    DEFAULT_PATIENT_ID_PREFIX,
    DEFAULT_STATE_DIR,
    DEFAULT_STUDIES_METADATA_CSV,
    DEFAULT_UIDROOT,
)
from .dicom_utils import series_information, unique_patient_ids
from .hash_clinical import hash_clinical_csvs
from .ocr_deidentify import perform_ocr
from .output_dir import copy_and_organize_parallel
from .pseudo import PseudonymGenerator
from .version import __version__
from pydantic import BaseModel, Field

INPUT_DIR: Path = Path("/input")
OUTPUT_DIR: Path = Path("/output")
CONFIG_FILE: Path = Path("/config/config.json")

# Remove default handler
logger.remove()

# Add my own handler with a custom format (no {name})
logger.add(
    sink=sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "| <level>{level: <8}</level> | "
    "{function}:{line} - <level>{message}</level>",
)

cli = typer.Typer(add_completion=False)
utils_cli = typer.Typer()
cli.add_typer(utils_cli, name="utils", help="Additional utilities")

# Input settings configuration
class Settings(BaseModel):
    site_id: str | None = None
    project_id: str | None = None

    input_dir: Path = Path("/input")
    output_dir: Path = Path("/output")
    pepper: str | None = None
    bscan_dcm_deidentify: bool = True
    dcm_deidentify: bool = True
    pseudonymize: bool = False
    ocr: bool = False
    paddle_ocr: bool = False

    threads: int = DEFAULT_CPU_THREADS
    hierarchical: bool = True
    verbose: bool = False
    version: bool | None = None
    pseudonym_prefix: str = "{site_id}_"
    state_dir: str = str(DEFAULT_STATE_DIR)

    @classmethod
    def from_config_file(cls, path: Path):
        if path.exists():
            with open(path) as f:
                return cls(**json.load(f))
        return cls()
    
def merge_settings(config: Settings, cli: dict) -> Settings:
    data = config.model_dump()

    for key, value in cli.items():
        if value is not None:
            data[key] = value

    return Settings(**data)

# Other utils
def _create_secret_key() -> str:
    u = uuid7.create().hex
    d = luhn.calc_check_digit(u, alphabet="0123456789abcdef")
    return f"{u}{d}"

def _valid_secret_key(secret_key: str) -> bool:
    if len(secret_key) != 33:
        return False
    return luhn.is_valid(secret_key, alphabet="0123456789abcdef")

def _make_pseudonym_generator(
    state_dir: str,
    site_id: str,
    pseudonym_prefix: str,
) -> PseudonymGenerator:
    return PseudonymGenerator(
        f"{state_dir}/{site_id}",
        pseudonym_prefix.format(site_id=site_id),
    )

def _header_info() -> str:
    return textwrap.dedent(
        f"""
    ██╗     ███████╗████████╗██╗  ██╗███████╗
    ██║     ██╔════╝╚══██╔══╝██║  ██║██╔════╝
    ██║     █████╗     ██║   ███████║█████╗
    ██║     ██╔══╝     ██║   ██╔══██║██╔══╝
    ███████╗███████╗   ██║   ██║  ██║███████╗
    ╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝
    Version: {__version__}
    "Lethe" DICOM Anonymization Tool, by CBML, FORTH-ICS
    Licensed under the EUPL v1.2
    Provided "as is" without warranty. Use at your own risk.

    """,
    )

def version_callback(value: bool):
    console = Console()
    if value:
        console.print(_header_info(), justify="left")
        console.print("Default settings", style="bold underline", justify="left")
        console.print(f"UID root: {DEFAULT_UIDROOT}")
        console.print(f"Patient ID prefix: {DEFAULT_PATIENT_ID_PREFIX}")
        console.print(f"Studies metadata CSV: {DEFAULT_STUDIES_METADATA_CSV}")
        console.print(f"Ignore CSV prefix: {DEFAULT_IGNORE_CSV_PREFIX}")
        console.print(f"State directory: {DEFAULT_STATE_DIR}")
        console.print(f"CPU threads: {DEFAULT_CPU_THREADS}")
        raise typer.Exit()

@utils_cli.command(help="Create a new 'secret' key to use for anonymization")
def secret():
    secret = _create_secret_key()
    console = Console()
    console.print(f"[bold][magenta]{secret}[/]")

@utils_cli.command(
    help="Extract and print the unique Series descriptions from input DICOM files"
)
def series_info(
    input_dir: Annotated[
        Path,
        typer.Argument(
            help="Input directory to read DICOM files from", show_default=True
        ),
    ] = INPUT_DIR,
    grouped: Annotated[
        bool,
        typer.Option("--grouped/--ungrouped", help="Group series by description"),
    ] = True,
    csv: Annotated[
        bool,
        typer.Option("--csv", help="Print series information in CSV format"),
    ] = False,
):
    series_info_list = series_information(input_dir)
    # UnGrouped but sorted by PatientID:
    if not grouped:
        if csv:
            import clevercsv

            writer = clevercsv.writer(sys.stdout, "excel")

            writer.writerow(
                [
                    "PatientID",
                    "StudyUID",
                    "SeriesUID",
                    "Modality",
                    "SeriesDescription",
                    "ImageCount",
                ]
            )

            for info in series_info_list:
                writer.writerow(
                    [
                        info.patient_id,
                        info.study_uid,
                        info.series_uid,
                        info.modality,
                        info.series_description,
                        f"{info.image_count}",
                    ]
                )
            return

        console = Console()

        table = Table(title="Series information")
        table.add_column("PatientID")
        table.add_column("StudyUID")
        table.add_column("SeriesUID")
        table.add_column("Modality")
        table.add_column("SeriesDescription")
        table.add_column("ImageCount")

        for info in series_info_list:
            table.add_row(
                info.patient_id,
                info.study_uid,
                info.series_uid,
                info.modality,
                info.series_description,
                f"{info.image_count}",
            )
        console.print()
        console.print(table)
        return
    # Grouped by SeriesDescription:
    key: attrgetter[str] = attrgetter("series_description")
    series_info = sorted(series_info_list, key=key)

    rows: list[tuple[str]] = []
    total_count = 0
    total_img_count = 0
    for descr, g in groupby(series_info, key):
        infos = list(g)
        total_count += len(infos)
        total_img_count += sum(i.image_count for i in infos)
        modalities = set(i.modality for i in infos)
        pids_cnt = len(set(i.patient_id for i in infos))
        studies_cnt = len(set((i.patient_id, i.study_uid) for i in infos))
        rows.append(
            (
                descr,
                ",".join(modalities),
                f"{pids_cnt}",
                f"{studies_cnt}",
                f"{len(infos)}",
            )
        )

    if csv:
        import clevercsv

        writer = clevercsv.writer(sys.stdout, "excel")

        writer.writerow(
            [
                "series_description",
                "modalities",
                "patients_count",
                "studies_count",
                "series_count",
            ]
        )

        for row in rows:
            writer.writerow(row)
        return

    console = Console()

    table = Table(title="Series information (Series are grouped by their descriptions)")

    table.add_column("Series Description", justify="left", style="bold", no_wrap=True)
    table.add_column("Modalities", style="magenta")
    table.add_column("Patients count")
    table.add_column("Studies count")
    table.add_column("Series count", style="green")

    pids = set(i.patient_id for i in series_info)
    studies = set((i.patient_id, i.study_uid) for i in series_info)
    for row in rows:
        table.add_row(*row)
    console.print()
    console.print(table)
    console.print(f"Total count of unique Patients: {len(pids)}", style="bold")
    console.print(f"Total count of unique Studies: {len(studies)}", style="bold")
    console.print(f"Total count of unique Series: {total_count}", style="bold")
    console.print(f"Total count of DICOM files: {total_img_count}", style="bold")

@utils_cli.command(
    help="Export the mappings from source patient ids to the pseunymized ones"
)
def export_lookup(
    site_id: Annotated[
        str,
        typer.Argument(
            help="The SITE-ID provided by the EUCAIM Technical team",
        ),
    ],
    pseudonym_prefix: Annotated[
        str,
        typer.Option(
            help="The prefix to use for the patient's pseudonym id. You can use it as a template, passing '{site_id}' somewhere in it",
            show_default=True,
        ),
    ] = "{site_id}_",
    state_dir: Annotated[
        str,
        typer.Option(
            help="The directory to use for storing state like lookup tables",
            show_default=True,
        ),
    ] = str(DEFAULT_STATE_DIR),
    csv: Annotated[
        bool,
        typer.Option("--csv", help="Export mappings in CSV format"),
    ] = False,
    tsv: Annotated[
        bool,
        typer.Option("--tsv", help="Export mappings in TSV format"),
    ] = False,
):
    pseudonym_gen = _make_pseudonym_generator(
        state_dir=state_dir,
        site_id=site_id,
        pseudonym_prefix=pseudonym_prefix,
    )

    if csv:
        pseudonym_gen.export_pseudonyms(dialect="excel")
        return
    if tsv:
        pseudonym_gen.export_pseudonyms(dialect="excel-tab")
        return

    console = Console()

    table = Table(title="Patient ID Lookup Table")
    table.add_column("Source PatientID")
    table.add_column("Pseudonym")

    for source_id, pseudonym in pseudonym_gen.items():
        table.add_row(source_id, pseudonym)
    console.print()
    console.print(table)

# Main functions
@cli.command(help="Run the DICOM anonymization pipeline")
def run(
    # Related to encryption
    site_id: Annotated[
        str | None,
        typer.Argument(
            help="The SITE-ID provided by the EUCAIM Technical team"
        )
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Argument(
            help="The PROJECT-ID provided by the DATA HOLDER team"
        )
    ] = None,
    pepper: Annotated[
        str | None,
        typer.Option(
            "--secret",
            help=(
                "Use the supplied key as the secret key for the anonymization."
                " This also enables 'pseudonymization', but in a diferrent way than the --pseudonymize flag:"
                " the secret key given here will be used for hashing patient ids, so the generated pseudonyms"
                " will be different than the ones generated with `--pseudonymize`."
            )
        )
    ] = None,

    # Options
    bscan_dcm_deidentify: Annotated[
        bool | None, 
        typer.Option(
        "--bs_hash/--no-bs_hash",
        help=(
                "Perform encryption of the patientIDs based on the BreastSCan scheme."
                "Uses the RSNA CTP anonymizer and the custom script."
            )
        )
    ] = None,
    dcm_deidentify: Annotated[
        bool | None, 
        typer.Option(
            "--ctp/--no-ctp",
            help=(
                    "Perform deidentification in the DICOM metadata in image files. "
                    "Uses the RSNA CTP anonymizer and the custom script"
                )
            )
    ] = None,
    pseudonymize: Annotated[
        bool | None, 
        typer.Option(
            "--pseudonymize",
            help=(
                "Perform pseudonymization by keeping a lookup table for patient ids in the `state-dir` folder."
                "The generated pseudonyms will be of the form `{pseudonym_prefix}{number}`, "
                "where the number is generated sequentially starting from 1 but reusing existing mappings."
            )
        )
    ] = None,
    ocr: Annotated[
        bool | None,
        typer.Option(
            "--ocr", 
            is_flag=True,
            help="Perform OCR (using Tesseract OCR)"
            )
    ] = None,
    paddle_ocr: Annotated[
        bool | None, 
        typer.Option(
            "--paddle-ocr", 
            is_flag=True,
            help="Perform OCR using PaddleOCR",
        )
    ] = None,
    threads: Annotated[
        int | None, 
        typer.Option(
            help="Number of threads that RSNA CTP and PaddleOCR (if enabled) will use"
        )
    ] = None,
    hierarchical: Annotated[
        bool | None, 
        typer.Option(
        "--hierarchical/--no-hierarchical",
            help=(
                "Output files will be organized into a hierarchical "
                "Patient / Study / Series folder structure using the anonymized UIDs "
                "as the folder names"
            )
        )
    ] = None,
    verbose: Annotated[
        bool | None, 
        typer.Option(
            "--verbose", 
            "-v",
            help="Enable verbose logging", 
            is_flag=True
        )
    ] = None,
    version: Annotated[
        bool | None, 
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            is_eager=True,
            help="Print version information",
    )] = None,
    pseudonym_prefix: Annotated[
        str | None, 
        typer.Option(
            help="The prefix to use for the patient's pseudonym id. You can use it as a template, passing '{site_id}'"
        )
    ] = None,
    state_dir: Annotated[
        str | None, 
        typer.Option(
            help="The directory to use for storing state like lookup tables",
            show_default=True, 
        )
    ] = None,
):
    config_settings = Settings.from_config_file(CONFIG_FILE)

    cli_values = {
        "site_id": site_id,
        "project_id": project_id,
        "input_dir": None,
        "output_dir": None,
        "pepper":pepper,
        "bscan_dcm_deidentify":bscan_dcm_deidentify,
        "dcm_deidentify":dcm_deidentify,
        "pseudonymize": pseudonymize,
        "ocr": ocr,
        "paddle_ocr": paddle_ocr,
        "threads":threads,
        "hierarchical":hierarchical,
        "verbose": verbose,
        "version":version,
        "pseudonym_prefix":pseudonym_prefix,
        "state_dir":state_dir
    }

    settings = merge_settings(config_settings, cli_values)
    site_id = settings.site_id
    project_id = settings.project_id
    input_dir = settings.input_dir
    output_dir = settings.output_dir
    pepper = settings.pepper
    bscan_dcm_deidentify = settings.bscan_dcm_deidentify
    dcm_deidentify = settings.dcm_deidentify
    pseudonymize = settings.pseudonymize
    ocr = settings.ocr
    paddle_ocr = settings.paddle_ocr
    threads = settings.threads
    hierarchical = settings.hierarchical
    verbose = settings.verbose
    version = settings.version
    pseudonym_prefix = settings.pseudonym_prefix
    state_dir = settings.state_dir

    if not site_id or not project_id:
        raise typer.BadParameter("site_id and project_id must be provided via CLI or config")
    
    if paddle_ocr and ocr:
        rich.print(
            "[red][bold]Error:[/bold] Cannot use both PaddleOCR and TesseractOCR: please choose one, use --help for usage information[/red]"
        )
        sys.exit(1)

    if not pepper:
        pepper = _create_secret_key()  # Create a time based (UUIDv7) string as secret
    elif not _valid_secret_key(pepper):
        rich.print("[red][bold]Error:[/bold] Invalid secret key[/red]")
        sys.exit(1)

    rich.print(_header_info())
    logger.info(f"Running with {threads} threads")
    pseudonym_gen: PseudonymGenerator | None = None
    if pseudonymize:
        pepper = site_id  # We overwrite the "secret" key to be the Site ID since we are pseudonymizing
        pseudonym_gen = _make_pseudonym_generator(
            state_dir=state_dir,
            site_id=site_id,
            pseudonym_prefix=pseudonym_prefix,
        )
        patient_ids = unique_patient_ids(input_dir)
        for patient_id in patient_ids:
            pseudonym_gen.assign(patient_id)

    if verbose:
        logger.debug(f"Using 'secret' key: {pepper}")

    # Step 1: Run OCR if enabled
    input_dir_images = input_dir.absolute()
    output_dir = output_dir.absolute()
    if ocr or paddle_ocr:
        ocr_output_dir = Path(tempfile.mkdtemp())
        perform_ocr(input_dir_images, ocr_output_dir, paddle_ocr, verbose, threads)
        input_dir_images = ocr_output_dir

    # Step 2: Run BreastScan patientID hashing.
    if bscan_dcm_deidentify:
        anon_script = Path(os.getcwd()) / "ctp" / "anon_BS.script"
        logger.info("Running BreastScan encryption scheme.")
        hash_output_dir = Path(tempfile.mkdtemp()) if hierarchical else output_dir
        hash_BS_id(
            input_dir=input_dir_images,
            output_dir=hash_output_dir,
            site_id=site_id,
            project_id=project_id,
            threads=threads,
        )
        input_dir_images = hash_output_dir
    else:
        anon_script = Path(os.getcwd()) / "ctp" / "anon.script"

    # Step 3: Run data anonymization
    if dcm_deidentify:
        ctp_output_dir = Path(tempfile.mkdtemp()) if hierarchical else output_dir
        run_ctp(
            input_dir=input_dir_images,
            output_dir=ctp_output_dir,
            anon_script=anon_script,
            site_id=site_id,
            pepper=pepper,
            threads=threads,
            pseudonym_generator=pseudonym_gen,
        )
        input_dir_images = ctp_output_dir

    # Step 4: Copy and organize files if hierarchical if needed
    if input_dir_images != output_dir:
        logger.info("Copying and reorganizing files.")
        #copy_and_organize(input_dir_images, output_dir, restructure=hierarchical)
        copy_and_organize_parallel(input_dir_images, output_dir, restructure=hierarchical, threads = threads) # Version with parallelization

    # Step 5: Hash any clinical CSVs found in the input directory:
    if dcm_deidentify:
        hash_clinical_csvs(
            input_dir,
            output_dir,
            secret_key=pepper,
            verbose=verbose,
            pseudonym_generator=pseudonym_gen,
        )

if __name__ == "__main__":
    cli(prog_name="")