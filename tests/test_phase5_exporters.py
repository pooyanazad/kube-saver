from kube_saver.exporters.helm_exporter import export_helm_values
from kube_saver.exporters.yaml_exporter import export_deployment_yaml
from kube_saver.models.core import CostInfo, Recommendation


def _recommendations() -> list[Recommendation]:
    return [
        Recommendation(
            target_kind="Deployment",
            target_name="demo",
            target_namespace="default",
            container_name="demo",
            resource_type="cpu-request",
            current_value="500m",
            suggested_value="150m",
            confidence="high",
            reason="low usage",
            estimated_savings=CostInfo.from_hourly(0.01),
        ),
        Recommendation(
            target_kind="Deployment",
            target_name="demo",
            target_namespace="default",
            container_name="demo",
            resource_type="memory-request",
            current_value="256Mi",
            suggested_value="96Mi",
            confidence="high",
            reason="low usage",
            estimated_savings=CostInfo.from_hourly(0.01),
        ),
    ]


def _manifest() -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "demo",
            "namespace": "default",
            "labels": {"app": "demo"},
            "annotations": {"team": "platform"},
        },
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "demo",
                            "resources": {
                                "requests": {"cpu": "500m", "memory": "256Mi"},
                                "limits": {"cpu": "1", "memory": "512Mi"},
                            },
                        }
                    ]
                }
            }
        },
    }


def test_export_deployment_yaml_preserves_metadata() -> None:
    result = export_deployment_yaml(_manifest(), _recommendations())
    assert result.valid is True
    assert result.manifest["metadata"]["labels"]["app"] == "demo"
    assert result.manifest["metadata"]["annotations"]["team"] == "platform"
    container = result.manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["resources"]["requests"]["cpu"] == "150m"
    assert container["resources"]["requests"]["memory"] == "96Mi"
    assert "500m -> 150m" in result.yaml_text


def test_export_deployment_yaml_dry_run() -> None:
    result = export_deployment_yaml(_manifest(), _recommendations(), dry_run=True)
    assert result.changes
    assert "kube-saver" in result.yaml_text


def test_export_helm_values_generates_comments_and_diff() -> None:
    result = export_helm_values(
        _recommendations(),
        namespace="default",
        workload_name="demo",
        chart_mode="helm3",
    )
    assert result.chart_mode == "helm3"
    assert result.values["resources"]["requests"]["cpu"] == "150m"
    assert result.values["resources"]["requests"]["memory"] == "96Mi"
    assert result.diff_lines
    assert "kube-saver (helm3)" in result.values_yaml
