"""
evaluador-calidad-ia · Evaluador automático de respuestas de agentes de IA.
Aplica rúbrica (precisión, seguridad, tono, completitud) y genera reportes HTML/JSON.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union, Optional, Dict, List

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("Instalá Jinja2: pip install jinja2")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
MAX_SCORE = 5


def load_test_cases(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Carga casos de prueba desde un archivo JSON."""
    filepath = Path(path) if path else BASE_DIR / "test_cases.json"
    if not filepath.exists():
        raise FileNotFoundError(f"Archivo de casos no encontrado: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_weighted_score(scores: Dict[str, int], rubric: Dict[str, dict]) -> float:
    """Calcula el score ponderado de un caso individual (0-100)."""
    weighted_sum = 0.0
    total_weight = 0.0
    for category, weight_info in rubric.items():
        weight = weight_info.get("weight", 0)
        score = scores.get(category, 0)
        weighted_sum += (score / MAX_SCORE) * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0
    return (weighted_sum / total_weight) * 100


def classify_severity(weighted_score: float) -> str:
    """Clasifica la severidad de un caso."""
    if weighted_score < 50:
        return "critical"
    if weighted_score < 75:
        return "warning"
    return "passed"


def evaluate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ejecuta la evaluación completa sobre los datos cargados."""
    rubric = data["rubric"]
    test_cases = data["test_cases"]
    metadata = data["metadata"]
    metadata["evaluated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    results = []
    category_totals: Dict[str, List[int]] = {k: [] for k in rubric}

    for case in test_cases:
        scores = case["scores"]
        weighted = compute_weighted_score(scores, rubric)

        for cat in rubric:
            category_totals[cat].append(scores.get(cat, 0))

        results.append({
            **case,
            "weighted_score": weighted,
            "severity": classify_severity(weighted),
        })

    categories_summary = {}
    for cat, values in category_totals.items():
        avg = sum(values) / len(values) if values else 0
        categories_summary[cat] = {
            "average": round(avg, 2),
            "percentage": round((avg / MAX_SCORE) * 100, 1),
            "weight": rubric[cat]["weight"],
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
        }

    global_weighted = sum(
        (cat_data["average"] / MAX_SCORE) * cat_data["weight"]
        for cat_data in categories_summary.values()
    )
    total_weight = sum(cat_data["weight"] for cat_data in categories_summary.values())
    global_score = (global_weighted / total_weight * 100) if total_weight else 0

    summary = {
        "total_cases": len(results),
        "global_score": round(global_score, 1),
        "critical_cases": sum(1 for r in results if r["severity"] == "critical"),
        "warning_cases": sum(1 for r in results if r["severity"] == "warning"),
        "passed_cases": sum(1 for r in results if r["severity"] == "passed"),
        "categories": categories_summary,
    }

    return {
        "metadata": metadata,
        "summary": summary,
        "results": results,
    }


def generate_html_report(
    evaluation: Dict[str, Any],
    output_path: Optional[Union[str, Path]] = None,
    template_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Genera el reporte HTML a partir de la evaluación."""
    template_dir = Path(template_path).parent if template_path else BASE_DIR
    template_name = Path(template_path).name if template_path else "report_template.html"

    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(template_name)

    html = template.render(**evaluation)

    out = Path(output_path) if output_path else BASE_DIR / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


def generate_json_report(
    evaluation: Dict[str, Any],
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    """Genera el reporte JSON a partir de la evaluación."""
    out = Path(output_path) if output_path else BASE_DIR / "report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=2)
    return out


def run(
    test_cases_path: Optional[Union[str, Path]] = None,
    output_format: str = "both",
    output_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Entry-point para CI/CD. 

    Args:
        test_cases_path: Ruta al JSON con los casos. Default: test_cases.json
        output_format: "html", "json", o "both"
        output_dir: Directorio de salida. Default: directorio del script

    Returns:
        Diccionario con los resultados de la evaluación.
    """
    data = load_test_cases(test_cases_path)
    evaluation = evaluate(data)
    out_dir = Path(output_dir) if output_dir else BASE_DIR

    if output_format in ("html", "both"):
        html_path = generate_html_report(evaluation, out_dir / "report.html")
        print(f"Reporte HTML generado: {html_path}")

    if output_format in ("json", "both"):
        json_path = generate_json_report(evaluation, out_dir / "report.json")
        print(f"Reporte JSON generado: {json_path}")

    critical_count = evaluation["summary"]["critical_cases"]
    global_score = evaluation["summary"]["global_score"]

    print(f"\nScore global: {global_score}%")
    print(f"Casos críticos: {critical_count}")
    print(f"Total evaluados: {evaluation['summary']['total_cases']}")

    if critical_count > 0:
        print("\n⚠ Se detectaron fallas críticas. Revisá el reporte.")

    return evaluation


def main():
    """CLI entry-point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluador automático de calidad para agentes de IA"
    )
    parser.add_argument(
        "-i", "--input",
        default=None,
        help="Ruta al archivo JSON con casos de prueba (default: test_cases.json)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["html", "json", "both"],
        default="both",
        help="Formato de salida del reporte (default: both)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directorio de salida para los reportes (default: directorio actual)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Modo CI: exit code 1 si hay fallas críticas",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=70.0,
        help="Score mínimo global para aprobar en CI (default: 70)",
    )

    args = parser.parse_args()
    evaluation = run(args.input, args.format, args.output_dir)

    if args.ci:
        has_critical = evaluation["summary"]["critical_cases"] > 0
        below_threshold = evaluation["summary"]["global_score"] < args.threshold

        if has_critical or below_threshold:
            reason = []
            if has_critical:
                reason.append(f"{evaluation['summary']['critical_cases']} falla(s) crítica(s)")
            if below_threshold:
                reason.append(
                    f"score {evaluation['summary']['global_score']}% < umbral {args.threshold}%"
                )
            print(f"\nCI FAILED: {', '.join(reason)}")
            sys.exit(1)
        else:
            print("\nCI PASSED")
            sys.exit(0)


if __name__ == "__main__":
    main()
