"""Transforms extracted assets into structured .md files."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Max lines per generated .md file before truncation
MAX_LINES = 500


def sanitize_filename(name: str) -> str:
    """Convert a name to a safe filename."""
    name = re.sub(r'[^\w\s\-.]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    return name.lower()[:100]


def _truncate(lines: list[str], max_lines: int = MAX_LINES) -> list[str]:
    """Truncate lines list and add a note if exceeded."""
    if len(lines) <= max_lines:
        return lines
    return lines[:max_lines] + [f"\n> ... truncated ({len(lines) - max_lines} more lines)\n"]


def _table_row(cells: list[str]) -> str:
    """Create a markdown table row."""
    return "| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in cells) + " |"


def _model_type_name(model_type) -> str:
    """Get a readable name for a SourceModelType enum value."""
    try:
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType
        return SourceModelType.Name(model_type)
    except Exception:
        return str(model_type)


def _is_ephemeral_name(name: str) -> bool:
    """Check if a service name looks like an ephemeral pod/job name.

    Filters out names with random suffixes like 'cron-tg5mg', 'web-7b4d6f8c9-xlk2p',
    or hex hashes that indicate K8s-generated pod names rather than real services.
    """
    # K8s pod suffix: ends with -<5 alphanum> (e.g. cron-tg5mg)
    if re.match(r'^.+-[a-z0-9]{5}$', name):
        return True
    # K8s replicaset pod: ends with -<8-10 hex>-<5 alphanum> (e.g. web-7b4d6f8c9-xlk2p)
    if re.match(r'^.+-[a-f0-9]{8,10}-[a-z0-9]{5}$', name):
        return True
    # Pure hex hash (e.g. a3f8c2d1e5)
    if re.match(r'^[a-f0-9]{8,}$', name):
        return True
    return False


class MarkdownGenerator:
    """Generates .md files from extracted infrastructure assets."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.resources_dir = output_dir / "resources"

    def _connector_dir(self, connector_name: str) -> Path:
        """Return resources/connectors/<sanitized_name>/, creating it if needed."""
        d = self.resources_dir / "connectors" / sanitize_filename(connector_name)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _write(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = content.split("\n")
        lines = _truncate(lines)
        path.write_text("\n".join(lines))
        logger.debug(f"Wrote {path}")

    def generate_all(self, connector_name: str, connector_type: str, assets: dict):
        """Generate all .md files for a single connector's assets."""
        self._generate_summary(connector_name, connector_type, assets)

        # Route to type-specific generators
        generators = {
            "GRAFANA": self._generate_grafana,
            "GRAFANA_LOKI": self._generate_grafana,
            "DATADOG": self._generate_datadog,
            "CLOUDWATCH": self._generate_cloudwatch,
            "KUBERNETES": self._generate_kubernetes,
            "EKS": self._generate_kubernetes_like,
            "GKE": self._generate_gke,
            "NEW_RELIC": self._generate_newrelic,
            "GITHUB": self._generate_github,
            "POSTGRES": self._generate_database,
            "MONGODB": self._generate_database,
            "CLICKHOUSE": self._generate_database,
            "SQL_DATABASE_CONNECTION": self._generate_database,
            "ELASTIC_SEARCH": self._generate_search_index,
            "OPEN_SEARCH": self._generate_search_index,
            "JIRA_CLOUD": self._generate_generic,
            "ARGOCD": self._generate_generic,
            "JENKINS": self._generate_generic,
            "SIGNOZ": self._generate_signoz,
            "SENTRY": self._generate_generic,
            "AZURE": self._generate_azure,
            "POSTHOG": self._generate_generic,
            "VICTORIA_LOGS": self._generate_generic,
            "CORALOGIX": self._generate_generic,
            "GCM": self._generate_gcm,
        }

        gen = generators.get(connector_type, self._generate_generic)
        gen(connector_name, connector_type, assets)

    def _generate_summary(self, connector_name: str, connector_type: str, assets: dict):
        """Generate connectors/<name>/_summary.md with resource counts."""
        lines = [
            f"# {connector_name} ({connector_type})",
            "",
            "## Extracted Resources",
            "",
            _table_row(["Resource Type", "Count"]),
            _table_row(["---", "---"]),
        ]

        for model_type, items in sorted(assets.items(), key=lambda x: _model_type_name(x[0])):
            name = _model_type_name(model_type)
            count = len(items) if isinstance(items, dict) else 0
            lines.append(_table_row([name, str(count)]))

        total = sum(len(v) for v in assets.values() if isinstance(v, dict))
        lines.extend(["", f"**Total resources:** {total}", ""])

        self._write(self._connector_dir(connector_name) / "_summary.md", "\n".join(lines))

    # ---- Grafana ----

    def _generate_grafana(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)

        # Datasources
        ds = assets.get(SMT.GRAFANA_DATASOURCE, {})
        if ds:
            lines = [f"# Grafana Datasources ({name})", "", _table_row(["Name", "Type", "UID"]), _table_row(["---", "---", "---"])]
            for uid, info in ds.items():
                n = info.get("name", uid)
                t = info.get("type", "unknown")
                lines.append(_table_row([n, t, uid]))
            self._write(cdir / "datasources.md", "\n".join(lines))

        # Dashboards
        dashboards = assets.get(SMT.GRAFANA_DASHBOARD, {})
        if dashboards:
            dash_dir = cdir / "dashboards"
            dash_dir.mkdir(parents=True, exist_ok=True)

            index_lines = [f"# Grafana Dashboards ({name})", "", f"**Total:** {len(dashboards)}", "",
                           _table_row(["Dashboard", "UID", "Panels"]), _table_row(["---", "---", "---"])]

            for uid, info in dashboards.items():
                title = info.get("title", uid)
                panels = info.get("panels", [])
                panel_count = len(panels) if isinstance(panels, list) else 0
                index_lines.append(_table_row([title, uid, str(panel_count)]))

                # Individual dashboard file
                dlines = [f"# {title}", f"**Source:** {name}", f"**UID:** {uid}", ""]
                if isinstance(panels, list) and panels:
                    dlines.extend([
                        "## Panels", "",
                        _table_row(["Panel", "Type", "Query/Metric"]),
                        _table_row(["---", "---", "---"]),
                    ])
                    for p in panels:
                        if isinstance(p, dict):
                            pname = p.get("title", "Untitled")
                            ptype = p.get("type", "")
                            expr = ""
                            targets = p.get("targets", [])
                            if isinstance(targets, list):
                                for t in targets[:1]:
                                    if isinstance(t, dict):
                                        expr = t.get("expr", t.get("query", ""))
                            dlines.append(_table_row([pname, ptype, str(expr)[:200]]))

                self._write(dash_dir / f"{sanitize_filename(title)}.md", "\n".join(dlines))

            self._write(cdir / "dashboards.md", "\n".join(index_lines))

        # Alerts
        alerts = assets.get(SMT.GRAFANA_ALERT_RULE, {})
        if alerts:
            lines = [f"# Grafana Alert Rules ({name})", "", f"**Total:** {len(alerts)}", "",
                     _table_row(["Alert", "State", "Labels"]), _table_row(["---", "---", "---"])]
            for uid, info in alerts.items():
                aname = info.get("title", info.get("name", uid))
                state = info.get("state", "")
                labels = info.get("labels", {})
                label_str = ", ".join(f"{k}={v}" for k, v in labels.items()) if isinstance(labels, dict) else ""
                lines.append(_table_row([aname, state, label_str]))
            self._write(cdir / "alerts.md", "\n".join(lines))

    # ---- Datadog ----

    def _generate_datadog(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)

        # Monitors
        monitors = assets.get(SMT.DATADOG_MONITOR, {})
        if monitors:
            lines = [f"# Datadog Monitors ({name})", "", f"**Total:** {len(monitors)}", "",
                     _table_row(["Monitor", "Type", "Tags"]), _table_row(["---", "---", "---"])]
            for uid, info in monitors.items():
                mname = info.get("name", uid)
                mtype = info.get("type", "")
                tags = ", ".join(info.get("tags", [])) if isinstance(info.get("tags"), list) else ""
                lines.append(_table_row([mname, mtype, tags]))
            self._write(cdir / "monitors.md", "\n".join(lines))

        # Services (filter out ephemeral pod/job names)
        services = assets.get(SMT.DATADOG_SERVICE, {})
        if services:
            filtered = {uid: info for uid, info in services.items()
                        if not _is_ephemeral_name(str(info.get("name", uid) if isinstance(info, dict) else uid))}
            if filtered:
                lines = [f"# Datadog Services ({name})", "", f"**Total:** {len(filtered)}", "",
                         _table_row(["Service", "Details"]), _table_row(["---", "---"])]
                for uid, info in filtered.items():
                    sname = info.get("name", uid) if isinstance(info, dict) else uid
                    details = ""
                    if isinstance(info, dict):
                        details = str({k: v for k, v in info.items() if k != "name"})[:200]
                    lines.append(_table_row([sname, details]))
                self._write(cdir / "services.md", "\n".join(lines))

        # Dashboards
        dashboards = assets.get(SMT.DATADOG_DASHBOARD, {})
        if dashboards:
            lines = [f"# Datadog Dashboards ({name})", "", f"**Total:** {len(dashboards)}", "",
                     _table_row(["Dashboard", "ID"]), _table_row(["---", "---"])]
            for uid, info in dashboards.items():
                dname = info.get("title", info.get("name", uid)) if isinstance(info, dict) else uid
                lines.append(_table_row([dname, uid]))
            self._write(cdir / "dashboards.md", "\n".join(lines))

    # ---- CloudWatch ----

    def _generate_cloudwatch(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)

        # Metrics (namespace -> region -> metric_name -> {Dimensions, DimensionNames})
        metrics = assets.get(SMT.CLOUDWATCH_METRIC, {})
        if metrics:
            lines = [f"# CloudWatch Metrics ({name})", ""]
            total_metrics = 0
            for namespace, regions in metrics.items():
                if not isinstance(regions, dict):
                    continue
                for region, metric_map in regions.items():
                    if not isinstance(metric_map, dict):
                        continue
                    total_metrics += len(metric_map)
            lines.append(f"**Total namespaces:** {len(metrics)}  |  **Total metrics:** {total_metrics}")
            lines.append("")
            for namespace in sorted(metrics.keys()):
                regions = metrics[namespace]
                if not isinstance(regions, dict):
                    continue
                lines.append(f"## {namespace}")
                lines.append("")
                for region, metric_map in regions.items():
                    if not isinstance(metric_map, dict):
                        continue
                    lines.extend([
                        _table_row(["Metric", "Dimensions"]),
                        _table_row(["---", "---"]),
                    ])
                    for metric_name in sorted(metric_map.keys()):
                        minfo = metric_map[metric_name]
                        dim_names = minfo.get("DimensionNames", []) if isinstance(minfo, dict) else []
                        lines.append(_table_row([metric_name, ", ".join(dim_names)]))
                lines.append("")
            self._write(cdir / "metrics.md", "\n".join(lines))

        # Log Groups (region -> {log_groups: [names]})
        log_groups = assets.get(SMT.CLOUDWATCH_LOG_GROUP, {})
        if log_groups:
            all_names = []
            for uid, info in log_groups.items():
                if isinstance(info, dict) and "log_groups" in info:
                    all_names.extend(info["log_groups"])
                else:
                    all_names.append(info.get("name", uid) if isinstance(info, dict) else uid)
            lines = [f"# CloudWatch Log Groups ({name})", "", f"**Total:** {len(all_names)}", "",
                     _table_row(["Log Group"]), _table_row(["---"])]
            for lg in sorted(all_names):
                lines.append(_table_row([lg]))
            self._write(cdir / "log_groups.md", "\n".join(lines))

        # Log Group Queries (log_group -> {queries: [query_strings]})
        log_queries = assets.get(SMT.CLOUDWATCH_LOG_GROUP_QUERY, {})
        if log_queries:
            lines = [f"# CloudWatch Log Insights Queries ({name})", "", f"**Total log groups with queries:** {len(log_queries)}", "",
                     _table_row(["Log Group", "Queries"]), _table_row(["---", "---"])]
            for log_group, info in sorted(log_queries.items()):
                queries = info.get("queries", []) if isinstance(info, dict) else []
                lines.append(_table_row([log_group, str(len(queries))]))
            lines.append("")
            # Detail section
            for log_group, info in sorted(log_queries.items()):
                queries = info.get("queries", []) if isinstance(info, dict) else []
                if queries:
                    lines.extend([f"## {log_group}", ""])
                    for q in queries:
                        lines.append(f"- `{q}`")
                    lines.append("")
            self._write(cdir / "log_queries.md", "\n".join(lines))

        # Alarms (alarm_name -> raw AWS alarm dict)
        alarms = assets.get(SMT.CLOUDWATCH_ALARMS, {})
        if alarms:
            lines = [f"# CloudWatch Alarms ({name})", "", f"**Total:** {len(alarms)}", "",
                     _table_row(["Alarm", "Namespace", "Metric", "Statistic", "Threshold"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in alarms.items():
                if isinstance(info, dict):
                    aname = info.get("AlarmName", uid)
                    namespace = info.get("Namespace", "")
                    metric = info.get("MetricName", "")
                    stat = info.get("Statistic", info.get("ExtendedStatistic", ""))
                    threshold = info.get("Threshold", "")
                else:
                    aname, namespace, metric, stat, threshold = uid, "", "", "", ""
                lines.append(_table_row([aname, str(namespace), str(metric), str(stat), str(threshold)]))
            self._write(cdir / "alarms.md", "\n".join(lines))

        # Dashboards (dashboard_name -> {dashboard_name, dashboard_arn, widgets, region})
        dashboards = assets.get(SMT.CLOUDWATCH_DASHBOARD, {})
        if dashboards:
            lines = [f"# CloudWatch Dashboards ({name})", "", f"**Total:** {len(dashboards)}", "",
                     _table_row(["Dashboard", "Widgets", "Region"]), _table_row(["---", "---", "---"])]
            for uid, info in dashboards.items():
                if isinstance(info, dict):
                    dname = info.get("dashboard_name", uid)
                    widgets = info.get("widgets", [])
                    widget_count = len(widgets) if isinstance(widgets, list) else 0
                    region = info.get("region", "")
                else:
                    dname, widget_count, region = uid, 0, ""
                lines.append(_table_row([dname, str(widget_count), str(region)]))
            lines.append("")
            # Dashboard widget details
            for uid, info in dashboards.items():
                if not isinstance(info, dict):
                    continue
                dname = info.get("dashboard_name", uid)
                widgets = info.get("widgets", [])
                if not widgets:
                    continue
                lines.extend([f"## {dname}", "",
                              _table_row(["Widget", "Namespace", "Metric", "Statistic", "Period"]),
                              _table_row(["---", "---", "---", "---", "---"])])
                for w in widgets:
                    if isinstance(w, dict):
                        lines.append(_table_row([
                            w.get("widget_title", ""),
                            w.get("namespace", ""),
                            w.get("metric_name", ""),
                            w.get("statistic", ""),
                            str(w.get("period", "")),
                        ]))
                lines.append("")
            self._write(cdir / "dashboards.md", "\n".join(lines))

        # ECS Clusters (cluster_name -> {cluster_name, services, containers, region})
        ecs_clusters = assets.get(SMT.ECS_CLUSTER, {})
        if ecs_clusters:
            lines = [f"# ECS Clusters ({name})", "", f"**Total:** {len(ecs_clusters)}", "",
                     _table_row(["Cluster", "Services", "Containers", "Region"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in ecs_clusters.items():
                if isinstance(info, dict):
                    cname = info.get("cluster_name", uid)
                    services = info.get("services", [])
                    containers = info.get("containers", [])
                    region = info.get("region", "")
                else:
                    cname, services, containers, region = uid, [], [], ""
                lines.append(_table_row([cname, str(len(services)), str(len(containers)), str(region)]))
            lines.append("")
            # Detail per cluster
            for uid, info in ecs_clusters.items():
                if not isinstance(info, dict):
                    continue
                cname = info.get("cluster_name", uid)
                services = info.get("services", [])
                containers = info.get("containers", [])
                if services or containers:
                    lines.append(f"## {cname}")
                    lines.append("")
                    if services:
                        lines.append(f"**Services:** {', '.join(services)}")
                        lines.append("")
                    if containers:
                        lines.append(f"**Containers:** {', '.join(containers)}")
                        lines.append("")
            self._write(cdir / "ecs_clusters.md", "\n".join(lines))

        # ECS Tasks (task_arn -> {taskArn, clusterName, status, container_name, ...})
        ecs_tasks = assets.get(SMT.ECS_TASK, {})
        if ecs_tasks:
            lines = [f"# ECS Tasks ({name})", "", f"**Total:** {len(ecs_tasks)}", "",
                     _table_row(["Task", "Cluster", "Container", "Status"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in ecs_tasks.items():
                if isinstance(info, dict):
                    task_arn = info.get("taskArn", uid)
                    task_id = task_arn.split("/")[-1] if "/" in task_arn else task_arn
                    cluster = info.get("clusterName", "")
                    container = info.get("container_name", "")
                    status = info.get("status", "")
                else:
                    task_id, cluster, container, status = uid, "", "", ""
                lines.append(_table_row([task_id, str(cluster), str(container), str(status)]))
            self._write(cdir / "ecs_tasks.md", "\n".join(lines))

        # RDS Instances (db_id -> raw AWS describe response + db_names)
        rds_instances = assets.get(SMT.RDS_INSTANCES, {})
        if rds_instances:
            lines = [f"# RDS Instances ({name})", "", f"**Total:** {len(rds_instances)}", "",
                     _table_row(["Instance", "Engine", "Class", "Status", "Databases"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in rds_instances.items():
                if isinstance(info, dict):
                    db_id = info.get("DBInstanceIdentifier", uid)
                    engine = info.get("Engine", "")
                    engine_ver = info.get("EngineVersion", "")
                    db_class = info.get("DBInstanceClass", "")
                    status = info.get("DBInstanceStatus", "")
                    db_names = info.get("db_names", [])
                    db_str = ", ".join(db_names) if isinstance(db_names, list) else ""
                else:
                    db_id, engine, engine_ver, db_class, status, db_str = uid, "", "", "", "", ""
                engine_full = f"{engine} {engine_ver}".strip() if engine else ""
                lines.append(_table_row([db_id, engine_full, str(db_class), str(status), db_str[:100]]))
            self._write(cdir / "rds_instances.md", "\n".join(lines))

    # ---- Kubernetes / EKS / GKE ----

    def _generate_kubernetes(self, name: str, ctype: str, assets: dict):
        self._generate_k8s_resources(name, ctype, assets, "KUBERNETES")

    def _generate_kubernetes_like(self, name: str, ctype: str, assets: dict):
        self._generate_k8s_resources(name, ctype, assets, ctype)

    def _generate_k8s_resources(self, name: str, ctype: str, assets: dict, prefix: str):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        # Map prefix to model types
        type_map = {
            "KUBERNETES": {
                "namespace": SMT.KUBERNETES_NAMESPACE, "service": SMT.KUBERNETES_SERVICE,
                "deployment": SMT.KUBERNETES_DEPLOYMENT, "ingress": SMT.KUBERNETES_INGRESS,
                "hpa": SMT.KUBERNETES_HPA, "replicaset": SMT.KUBERNETES_REPLICASET,
                "statefulset": SMT.KUBERNETES_STATEFULSET,
                "network_policy": SMT.KUBERNETES_NETWORK_POLICY,
            },
            "EKS": {
                "namespace": SMT.EKS_NAMESPACE, "service": SMT.EKS_SERVICE,
                "deployment": SMT.EKS_DEPLOYMENT, "ingress": SMT.EKS_INGRESS,
                "hpa": SMT.EKS_HPA, "replicaset": SMT.EKS_REPLICASET,
                "statefulset": SMT.EKS_STATEFULSET, "network_policy": SMT.EKS_NETWORK_POLICY,
            },
            "GKE": {
                "namespace": SMT.GKE_NAMESPACE, "service": SMT.GKE_SERVICE,
                "deployment": SMT.GKE_DEPLOYMENT, "ingress": SMT.GKE_INGRESS,
                "hpa": SMT.GKE_HPA, "replicaset": SMT.GKE_REPLICASET,
                "statefulset": SMT.GKE_STATEFULSET, "network_policy": SMT.GKE_NETWORK_POLICY,
            },
        }

        types = type_map.get(prefix, {})
        cdir = self._connector_dir(name)

        # Write per-resource-type files
        for resource_name, model_type in types.items():
            items = assets.get(model_type, {})
            if not items:
                continue

            lines = [f"# {resource_name.replace('_', ' ').title()}s ({name})", "", f"**Total:** {len(items)}", ""]

            if resource_name == "deployment":
                lines.extend([_table_row(["Name", "Replicas", "Image"]), _table_row(["---", "---", "---"])])
                for uid, info in items.items():
                    dname = info.get("name", uid) if isinstance(info, dict) else uid
                    replicas = info.get("replicas", "") if isinstance(info, dict) else ""
                    image = info.get("image", "") if isinstance(info, dict) else ""
                    lines.append(_table_row([dname, str(replicas), str(image)[:100]]))
            elif resource_name == "service":
                lines.extend([_table_row(["Name", "Type", "Ports"]), _table_row(["---", "---", "---"])])
                for uid, info in items.items():
                    sname = info.get("name", uid) if isinstance(info, dict) else uid
                    stype = info.get("type", "") if isinstance(info, dict) else ""
                    ports = info.get("ports", "") if isinstance(info, dict) else ""
                    lines.append(_table_row([sname, str(stype), str(ports)[:100]]))
            elif resource_name == "namespace":
                for uid, info in items.items():
                    ns = info.get("name", uid) if isinstance(info, dict) else uid
                    lines.append(f"- {ns}")
            else:
                lines.extend([_table_row(["Name", "Details"]), _table_row(["---", "---"])])
                for uid, info in items.items():
                    iname = info.get("name", uid) if isinstance(info, dict) else uid
                    lines.append(_table_row([iname, ""]))

            lines.append("")
            self._write(cdir / f"{resource_name}s.md", "\n".join(lines))

    # ---- GKE (K8s + GCP resources) ----

    def _generate_gke(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        # First generate the K8s-style resources (namespaces, deployments, etc.)
        self._generate_k8s_resources(name, ctype, assets, "GKE")

        cdir = self._connector_dir(name)

        # GKE Clusters
        clusters = assets.get(SMT.GKE_CLUSTER, {})
        if clusters:
            lines = [f"# GKE Clusters ({name})", "", f"**Total:** {len(clusters)}", "",
                     _table_row(["Cluster", "Location", "Status"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in clusters.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("location", "")),
                        str(info.get("status", "")),
                    ]))
            self._write(cdir / "clusters.md", "\n".join(lines))

        # Compute Instances
        vms = assets.get(SMT.GCP_COMPUTE_INSTANCE, {})
        if vms:
            lines = [f"# Compute Engine Instances ({name})", "", f"**Total:** {len(vms)}", "",
                     _table_row(["Instance", "Zone", "Machine Type", "Status"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in vms.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("zone", "")),
                        str(info.get("machine_type", ""))[:60],
                        str(info.get("status", "")),
                    ]))
            self._write(cdir / "compute_instances.md", "\n".join(lines))

        # Instance Groups
        igs = assets.get(SMT.GCP_INSTANCE_GROUP, {})
        if igs:
            lines = [f"# Instance Groups ({name})", "", f"**Total:** {len(igs)}", "",
                     _table_row(["Group", "Zone", "Size"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in igs.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("zone", "")),
                        str(info.get("size", "")),
                    ]))
            self._write(cdir / "instance_groups.md", "\n".join(lines))

        # Storage Buckets
        buckets = assets.get(SMT.GCP_STORAGE_BUCKET, {})
        if buckets:
            lines = [f"# Cloud Storage Buckets ({name})", "", f"**Total:** {len(buckets)}", "",
                     _table_row(["Bucket", "Location", "Storage Class"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in buckets.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("location", "")),
                        str(info.get("storage_class", "")),
                    ]))
            self._write(cdir / "storage_buckets.md", "\n".join(lines))

        # Cloud SQL Instances
        sql_instances = assets.get(SMT.GCP_CLOUD_SQL_INSTANCE, {})
        if sql_instances:
            lines = [f"# Cloud SQL Instances ({name})", "", f"**Total:** {len(sql_instances)}", "",
                     _table_row(["Instance", "Database Version", "Tier", "State", "Region"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in sql_instances.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("database_version", "")),
                        str(info.get("tier", info.get("settings", {}).get("tier", ""))),
                        str(info.get("state", "")),
                        str(info.get("region", "")),
                    ]))
            self._write(cdir / "cloud_sql_instances.md", "\n".join(lines))

        # Cloud SQL Databases
        sql_dbs = assets.get(SMT.GCP_CLOUD_SQL_DATABASE, {})
        if sql_dbs:
            lines = [f"# Cloud SQL Databases ({name})", "", f"**Total:** {len(sql_dbs)}", "",
                     _table_row(["Database", "Instance", "Charset", "Collation"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in sql_dbs.items():
                if isinstance(info, dict):
                    ctx = info.get("gcp_context", {})
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(ctx.get("instance", "")),
                        str(info.get("charset", "")),
                        str(info.get("collation", "")),
                    ]))
            self._write(cdir / "cloud_sql_databases.md", "\n".join(lines))

        # Memorystore Redis
        redis = assets.get(SMT.GCP_MEMORYSTORE_REDIS, {})
        if redis:
            lines = [f"# Memorystore Redis ({name})", "", f"**Total:** {len(redis)}", "",
                     _table_row(["Instance", "Location", "Version", "Tier", "Memory GB", "State"]),
                     _table_row(["---", "---", "---", "---", "---", "---"])]
            for uid, info in redis.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("location", "")),
                        str(info.get("redis_version", "")),
                        str(info.get("tier", "")),
                        str(info.get("memory_size_gb", "")),
                        str(info.get("state", "")),
                    ]))
            self._write(cdir / "redis_instances.md", "\n".join(lines))

        # Alert Policies
        alerts = assets.get(SMT.GCP_ALERT_POLICY, {})
        if alerts:
            lines = [f"# Alert Policies ({name})", "", f"**Total:** {len(alerts)}", "",
                     _table_row(["Policy", "Display Name", "Enabled"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in alerts.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        str(uid).split("/")[-1],
                        str(info.get("display_name", info.get("displayName", ""))),
                        str(info.get("enabled", "")),
                    ]))
            self._write(cdir / "alert_policies.md", "\n".join(lines))

        # Notification Channels
        channels = assets.get(SMT.GCP_NOTIFICATION_CHANNEL, {})
        if channels:
            lines = [f"# Notification Channels ({name})", "", f"**Total:** {len(channels)}", "",
                     _table_row(["Channel", "Type", "Enabled"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in channels.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("display_name", info.get("displayName", uid)),
                        str(info.get("type", "")),
                        str(info.get("enabled", "")),
                    ]))
            self._write(cdir / "notification_channels.md", "\n".join(lines))

        # Cloud Functions
        functions = assets.get(SMT.GCP_CLOUD_FUNCTION, {})
        if functions:
            lines = [f"# Cloud Functions ({name})", "", f"**Total:** {len(functions)}", "",
                     _table_row(["Function", "Location", "Runtime", "State"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in functions.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("location", "")),
                        str(info.get("runtime", "")),
                        str(info.get("state", info.get("status", ""))),
                    ]))
            self._write(cdir / "cloud_functions.md", "\n".join(lines))

        # Cloud Run Services
        run_services = assets.get(SMT.GCP_CLOUD_RUN_SERVICE, {})
        if run_services:
            lines = [f"# Cloud Run Services ({name})", "", f"**Total:** {len(run_services)}", "",
                     _table_row(["Service", "Location", "URL"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in run_services.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("location", "")),
                        str(info.get("uri", info.get("url", "")))[:100],
                    ]))
            self._write(cdir / "cloud_run_services.md", "\n".join(lines))

        # Pub/Sub Topics
        topics = assets.get(SMT.GCP_PUBSUB_TOPIC, {})
        if topics:
            lines = [f"# Pub/Sub Topics ({name})", "", f"**Total:** {len(topics)}", ""]
            for uid, info in topics.items():
                topic_name = str(uid).split("/")[-1] if "/" in str(uid) else uid
                lines.append(f"- {topic_name}")
            self._write(cdir / "pubsub_topics.md", "\n".join(lines))

        # Pub/Sub Subscriptions
        subs = assets.get(SMT.GCP_PUBSUB_SUBSCRIPTION, {})
        if subs:
            lines = [f"# Pub/Sub Subscriptions ({name})", "", f"**Total:** {len(subs)}", "",
                     _table_row(["Subscription", "Topic"]),
                     _table_row(["---", "---"])]
            for uid, info in subs.items():
                if isinstance(info, dict):
                    sub_name = str(uid).split("/")[-1] if "/" in str(uid) else uid
                    topic = str(info.get("topic", "")).split("/")[-1]
                    lines.append(_table_row([sub_name, topic]))
            self._write(cdir / "pubsub_subscriptions.md", "\n".join(lines))

        # BigQuery Datasets
        bq_datasets = assets.get(SMT.GCP_BIGQUERY_DATASET, {})
        if bq_datasets:
            lines = [f"# BigQuery Datasets ({name})", "", f"**Total:** {len(bq_datasets)}", "",
                     _table_row(["Dataset", "Location"]),
                     _table_row(["---", "---"])]
            for uid, info in bq_datasets.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("dataset_id", uid),
                        str(info.get("location", "")),
                    ]))
            self._write(cdir / "bigquery_datasets.md", "\n".join(lines))

        # BigQuery Tables
        bq_tables = assets.get(SMT.GCP_BIGQUERY_TABLE, {})
        if bq_tables:
            lines = [f"# BigQuery Tables ({name})", "", f"**Total:** {len(bq_tables)}", "",
                     _table_row(["Table", "Dataset", "Type"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in bq_tables.items():
                if isinstance(info, dict):
                    ctx = info.get("gcp_context", {})
                    lines.append(_table_row([
                        info.get("table_id", uid),
                        str(uid).split("/")[0] if "/" in str(uid) else "",
                        str(info.get("type", "")),
                    ]))
            self._write(cdir / "bigquery_tables.md", "\n".join(lines))

        # VPC Networks
        vpcs = assets.get(SMT.GCP_VPC_NETWORK, {})
        if vpcs:
            lines = [f"# VPC Networks ({name})", "", f"**Total:** {len(vpcs)}", "",
                     _table_row(["Network", "Auto Create Subnets", "Routing Mode"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in vpcs.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("auto_create_subnetworks", "")),
                        str(info.get("routing_config", {}).get("routing_mode", "") if isinstance(info.get("routing_config"), dict) else ""),
                    ]))
            self._write(cdir / "vpc_networks.md", "\n".join(lines))

        # Subnetworks
        subnets = assets.get(SMT.GCP_SUBNETWORK, {})
        if subnets:
            lines = [f"# Subnetworks ({name})", "", f"**Total:** {len(subnets)}", "",
                     _table_row(["Subnet", "Region", "CIDR", "Network"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in subnets.items():
                if isinstance(info, dict):
                    network = str(info.get("network", "")).split("/")[-1]
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("region", "")),
                        str(info.get("ip_cidr_range", "")),
                        network,
                    ]))
            self._write(cdir / "subnetworks.md", "\n".join(lines))

        # Firewall Rules
        fw = assets.get(SMT.GCP_FIREWALL_RULE, {})
        if fw:
            lines = [f"# Firewall Rules ({name})", "", f"**Total:** {len(fw)}", "",
                     _table_row(["Rule", "Direction", "Priority", "Network"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in fw.items():
                if isinstance(info, dict):
                    network = str(info.get("network", "")).split("/")[-1]
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("direction", "")),
                        str(info.get("priority", "")),
                        network,
                    ]))
            self._write(cdir / "firewall_rules.md", "\n".join(lines))

        # Load Balancers
        lbs = assets.get(SMT.GCP_LOAD_BALANCER, {})
        if lbs:
            lines = [f"# Load Balancers ({name})", "", f"**Total:** {len(lbs)}", "",
                     _table_row(["Name", "Region", "IP", "Target"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in lbs.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("region", "")),
                        str(info.get("ip_address", info.get("IPAddress", "")))[:40],
                        str(info.get("target", "")).split("/")[-1][:60],
                    ]))
            self._write(cdir / "load_balancers.md", "\n".join(lines))

        # Secrets
        secrets = assets.get(SMT.GCP_SECRET, {})
        if secrets:
            lines = [f"# Secret Manager Secrets ({name})", "", f"**Total:** {len(secrets)}", ""]
            for uid, info in secrets.items():
                secret_name = str(uid).split("/")[-1] if "/" in str(uid) else uid
                lines.append(f"- {secret_name}")
            self._write(cdir / "secrets.md", "\n".join(lines))

        # Service Accounts
        sa = assets.get(SMT.GCP_SERVICE_ACCOUNT, {})
        if sa:
            lines = [f"# Service Accounts ({name})", "", f"**Total:** {len(sa)}", "",
                     _table_row(["Email", "Display Name", "Disabled"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in sa.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("email", uid),
                        str(info.get("display_name", info.get("displayName", ""))),
                        str(info.get("disabled", "")),
                    ]))
            self._write(cdir / "service_accounts.md", "\n".join(lines))

        # Log Sinks
        sinks = assets.get(SMT.GCP_LOG_SINK, {})
        if sinks:
            lines = [f"# Log Sinks ({name})", "", f"**Total:** {len(sinks)}", "",
                     _table_row(["Sink", "Destination"]),
                     _table_row(["---", "---"])]
            for uid, info in sinks.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("destination", ""))[:100],
                    ]))
            self._write(cdir / "log_sinks.md", "\n".join(lines))

        # Log Metrics
        log_metrics = assets.get(SMT.GCP_LOG_METRIC, {})
        if log_metrics:
            lines = [f"# Log-Based Metrics ({name})", "", f"**Total:** {len(log_metrics)}", "",
                     _table_row(["Metric", "Filter"]),
                     _table_row(["---", "---"])]
            for uid, info in log_metrics.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("filter", ""))[:150],
                    ]))
            self._write(cdir / "log_metrics.md", "\n".join(lines))

    # ---- GCM (Google Cloud Monitoring) ----

    def _generate_gcm(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)

        # Metrics
        metrics = assets.get(SMT.GCM_METRIC, {})
        if metrics:
            lines = [f"# GCM Metrics ({name})", "", f"**Total:** {len(metrics)}", ""]
            # Group by prefix (e.g. compute.googleapis.com, custom.googleapis.com)
            by_prefix: dict[str, list[str]] = {}
            for uid, info in metrics.items():
                metric_type = info.get("metric_type", uid) if isinstance(info, dict) else uid
                parts = str(metric_type).split("/", 1)
                prefix = parts[0] if len(parts) > 1 else "other"
                by_prefix.setdefault(prefix, []).append(metric_type)

            for prefix in sorted(by_prefix.keys()):
                metric_list = by_prefix[prefix]
                lines.extend([f"## {prefix} ({len(metric_list)})", ""])
                for m in sorted(metric_list):
                    lines.append(f"- `{m}`")
                lines.append("")
            self._write(cdir / "metrics.md", "\n".join(lines))

        # Dashboards
        dashboards = assets.get(SMT.GCM_DASHBOARD, {})
        if dashboards:
            lines = [f"# GCM Dashboards ({name})", "", f"**Total:** {len(dashboards)}", "",
                     _table_row(["Dashboard", "Widgets"]),
                     _table_row(["---", "---"])]
            for uid, info in dashboards.items():
                if isinstance(info, dict):
                    display = info.get("displayName", uid)
                    widgets = info.get("widgets", [])
                    widget_count = len(widgets) if isinstance(widgets, list) else 0
                    lines.append(_table_row([display, str(widget_count)]))
            self._write(cdir / "dashboards.md", "\n".join(lines))

        # Cloud Run Service Dashboards
        cr_dashboards = assets.get(SMT.GCM_CLOUD_RUN_SERVICE_DASHBOARD, {})
        if cr_dashboards:
            lines = [f"# Cloud Run Service Dashboards ({name})", "", f"**Total:** {len(cr_dashboards)}", "",
                     _table_row(["Service", "Region", "Metrics", "Console URL"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in cr_dashboards.items():
                if isinstance(info, dict):
                    svc = info.get("service_name", uid)
                    region = info.get("region", "")
                    metrics_list = info.get("metrics", [])
                    metric_count = len(metrics_list) if isinstance(metrics_list, list) else 0
                    url = info.get("url", "")
                    lines.append(_table_row([svc, region, str(metric_count), url[:80]]))
            self._write(cdir / "cloud_run_dashboards.md", "\n".join(lines))

    # ---- New Relic ----

    def _generate_newrelic(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)
        lines = [f"# New Relic ({name})", ""]

        policies = assets.get(SMT.NEW_RELIC_POLICY, {})
        if policies:
            lines.extend([f"## Alert Policies ({len(policies)})", "",
                          _table_row(["Policy", "ID"]), _table_row(["---", "---"])])
            for uid, info in policies.items():
                pname = info.get("name", uid) if isinstance(info, dict) else uid
                lines.append(_table_row([pname, uid]))
            lines.append("")

        entities = assets.get(SMT.NEW_RELIC_ENTITY, {})
        if entities:
            lines.extend([f"## Entities ({len(entities)})", "",
                          _table_row(["Entity", "Type"]), _table_row(["---", "---"])])
            for uid, info in entities.items():
                ename = info.get("name", uid) if isinstance(info, dict) else uid
                etype = info.get("type", "") if isinstance(info, dict) else ""
                lines.append(_table_row([ename, str(etype)]))
            lines.append("")

        self._write(cdir / "details.md", "\n".join(lines))

    # ---- GitHub ----

    def _generate_github(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)
        lines = [f"# GitHub ({name})", ""]

        repos = assets.get(SMT.GITHUB_REPOSITORY, {})
        if repos:
            lines.extend([f"## Repositories ({len(repos)})", "",
                          _table_row(["Repository", "Description"]), _table_row(["---", "---"])])
            for uid, info in repos.items():
                rname = info.get("name", uid) if isinstance(info, dict) else uid
                desc = info.get("description", "") if isinstance(info, dict) else ""
                lines.append(_table_row([rname, str(desc)[:200]]))
            lines.append("")

        members = assets.get(SMT.GITHUB_MEMBER, {})
        if members:
            lines.extend([f"## Members ({len(members)})", ""])
            for uid, info in members.items():
                mname = info.get("login", info.get("name", uid)) if isinstance(info, dict) else uid
                lines.append(f"- {mname}")
            lines.append("")

        self._write(cdir / "details.md", "\n".join(lines))

    # ---- Databases ----

    def _generate_database(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)
        lines = [f"# Database ({name}) - {ctype}", ""]

        for model_type, items in assets.items():
            if not items:
                continue
            mt_name = _model_type_name(model_type)
            lines.extend([f"## {mt_name} ({len(items)})", "",
                          _table_row(["Name", "Details"]), _table_row(["---", "---"])])
            for uid, info in items.items():
                iname = info.get("name", info.get("table_name", uid)) if isinstance(info, dict) else uid
                details = ""
                if isinstance(info, dict):
                    cols = info.get("columns", info.get("fields", []))
                    if isinstance(cols, list):
                        details = ", ".join(str(c)[:50] for c in cols[:10])
                lines.append(_table_row([iname, details[:200]]))
            lines.append("")

        self._write(cdir / "tables.md", "\n".join(lines))

    # ---- Search Indexes ----

    def _generate_search_index(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)
        lines = [f"# {ctype} ({name})", ""]

        for model_type, items in assets.items():
            if not items:
                continue
            mt_name = _model_type_name(model_type)
            lines.extend([f"## {mt_name} ({len(items)})", "",
                          _table_row(["Index/Resource", "Details"]), _table_row(["---", "---"])])
            for uid, info in items.items():
                iname = info.get("name", uid) if isinstance(info, dict) else uid
                lines.append(_table_row([iname, ""]))
            lines.append("")

        self._write(cdir / "indices.md", "\n".join(lines))

    # ---- Azure ----

    def _generate_azure(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)

        # ---- Core: Resource Groups ----
        rgs = assets.get(SMT.AZURE_RESOURCE_GROUP, {})
        if rgs:
            lines = [f"# Azure Resource Groups ({name})", "", f"**Total:** {len(rgs)}", "",
                     _table_row(["Resource Group", "Location", "State"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in rgs.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("location", "")),
                        str(info.get("provisioning_state", "")),
                    ]))
            self._write(cdir / "resource_groups.md", "\n".join(lines))

        # ---- Core: Log Analytics Workspaces ----
        ws = assets.get(SMT.AZURE_WORKSPACE, {})
        if ws:
            lines = [f"# Azure Log Analytics Workspaces ({name})", "", f"**Total:** {len(ws)}", "",
                     _table_row(["Workspace", "ID", "Location"]),
                     _table_row(["---", "---", "---"])]
            for uid, info in ws.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("customer_id", uid)),
                        str(info.get("location", "")),
                    ]))
            self._write(cdir / "workspaces.md", "\n".join(lines))

        # ---- Core: Generic Resources ----
        resources = assets.get(SMT.AZURE_RESOURCE, {})
        if resources:
            lines = [f"# Azure Resources ({name})", "", f"**Total:** {len(resources)}", "",
                     _table_row(["Resource", "Type", "Location", "Resource Group"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in resources.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("type", "")),
                        str(info.get("location", "")),
                        str(info.get("resource_group", "")),
                    ]))
            self._write(cdir / "resources.md", "\n".join(lines))

        # ---- AKS: Clusters ----
        aks_clusters = assets.get(SMT.AZURE_AKS_CLUSTER, {})
        if aks_clusters:
            lines = [f"# AKS Clusters ({name})", "", f"**Total:** {len(aks_clusters)}", "",
                     _table_row(["Cluster", "Location", "K8s Version", "State", "Resource Group"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in aks_clusters.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("location", "")),
                        str(info.get("kubernetes_version", "")),
                        str(info.get("provisioning_state", "")),
                        str(info.get("resource_group", "")),
                    ]))
            self._write(cdir / "aks_clusters.md", "\n".join(lines))

        # ---- AKS: K8s-style resources (namespaces, deployments, services, etc.) ----
        aks_k8s_types = {
            "namespace": SMT.AZURE_AKS_NAMESPACE,
            "deployment": SMT.AZURE_AKS_DEPLOYMENT,
            "service": SMT.AZURE_AKS_SERVICE,
            "ingress": SMT.AZURE_AKS_INGRESS,
            "hpa": SMT.AZURE_AKS_HPA,
            "replicaset": SMT.AZURE_AKS_REPLICASET,
            "statefulset": SMT.AZURE_AKS_STATEFULSET,
            "network_policy": SMT.AZURE_AKS_NETWORK_POLICY,
        }
        for resource_name, model_type in aks_k8s_types.items():
            items = assets.get(model_type, {})
            if not items:
                continue
            lines = [f"# AKS {resource_name.replace('_', ' ').title()}s ({name})", "",
                     f"**Total:** {len(items)}", ""]
            if resource_name == "namespace":
                for uid, info in items.items():
                    ns = info.get("metadata", {}).get("name", uid) if isinstance(info, dict) else uid
                    cluster = info.get("aks_context", {}).get("cluster", "") if isinstance(info, dict) else ""
                    lines.append(f"- {cluster}/{ns}" if cluster else f"- {ns}")
            elif resource_name == "deployment":
                lines.extend([_table_row(["Name", "Namespace", "Cluster", "Replicas", "Ready"]),
                              _table_row(["---", "---", "---", "---", "---"])])
                for uid, info in items.items():
                    if isinstance(info, dict):
                        meta = info.get("metadata", {})
                        spec = info.get("spec", {})
                        status = info.get("status", {})
                        ctx = info.get("aks_context", {})
                        lines.append(_table_row([
                            meta.get("name", uid), meta.get("namespace", ""),
                            ctx.get("cluster", ""),
                            str(spec.get("replicas", "")),
                            str(status.get("ready_replicas", "")),
                        ]))
            elif resource_name == "service":
                lines.extend([_table_row(["Name", "Namespace", "Cluster", "Type", "Cluster IP"]),
                              _table_row(["---", "---", "---", "---", "---"])])
                for uid, info in items.items():
                    if isinstance(info, dict):
                        meta = info.get("metadata", {})
                        spec = info.get("spec", {})
                        ctx = info.get("aks_context", {})
                        lines.append(_table_row([
                            meta.get("name", uid), meta.get("namespace", ""),
                            ctx.get("cluster", ""),
                            str(spec.get("type", "")),
                            str(spec.get("cluster_ip", "")),
                        ]))
            elif resource_name == "hpa":
                lines.extend([_table_row(["Name", "Namespace", "Cluster", "Min", "Max", "Current"]),
                              _table_row(["---", "---", "---", "---", "---", "---"])])
                for uid, info in items.items():
                    if isinstance(info, dict):
                        meta = info.get("metadata", {})
                        spec = info.get("spec", {})
                        status = info.get("status", {})
                        ctx = info.get("aks_context", {})
                        lines.append(_table_row([
                            meta.get("name", uid), meta.get("namespace", ""),
                            ctx.get("cluster", ""),
                            str(spec.get("min_replicas", "")),
                            str(spec.get("max_replicas", "")),
                            str(status.get("current_replicas", "")),
                        ]))
            else:
                lines.extend([_table_row(["Name", "Namespace", "Cluster"]),
                              _table_row(["---", "---", "---"])])
                for uid, info in items.items():
                    if isinstance(info, dict):
                        meta = info.get("metadata", {})
                        ctx = info.get("aks_context", {})
                        lines.append(_table_row([
                            meta.get("name", uid), meta.get("namespace", ""),
                            ctx.get("cluster", ""),
                        ]))
            lines.append("")
            self._write(cdir / f"aks_{resource_name}s.md", "\n".join(lines))

        # ---- Compute: Virtual Machines ----
        vms = assets.get(SMT.AZURE_VIRTUAL_MACHINE, {})
        if vms:
            lines = [f"# Azure Virtual Machines ({name})", "", f"**Total:** {len(vms)}", "",
                     _table_row(["VM", "Size", "OS", "Location", "State", "Resource Group"]),
                     _table_row(["---", "---", "---", "---", "---", "---"])]
            for uid, info in vms.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("vm_size", "")),
                        str(info.get("os_type", "")),
                        str(info.get("location", "")),
                        str(info.get("provisioning_state", "")),
                        str(info.get("resource_group", "")),
                    ]))
            self._write(cdir / "virtual_machines.md", "\n".join(lines))

        # ---- Compute: VM Scale Sets ----
        vmss = assets.get(SMT.AZURE_VMSS, {})
        if vmss:
            lines = [f"# Azure VM Scale Sets ({name})", "", f"**Total:** {len(vmss)}", "",
                     _table_row(["VMSS", "SKU", "Capacity", "Location", "State"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in vmss.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("sku_name", "")),
                        str(info.get("capacity", "")),
                        str(info.get("location", "")),
                        str(info.get("provisioning_state", "")),
                    ]))
            self._write(cdir / "vmss.md", "\n".join(lines))

        # ---- Storage: Accounts ----
        sa = assets.get(SMT.AZURE_STORAGE_ACCOUNT, {})
        if sa:
            lines = [f"# Azure Storage Accounts ({name})", "", f"**Total:** {len(sa)}", "",
                     _table_row(["Account", "Kind", "SKU", "Tier", "Location"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in sa.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("kind", "")),
                        str(info.get("sku_name", "")),
                        str(info.get("access_tier", "")),
                        str(info.get("location", "")),
                    ]))
            self._write(cdir / "storage_accounts.md", "\n".join(lines))

        # ---- Storage: Blob Containers ----
        blobs = assets.get(SMT.AZURE_BLOB_CONTAINER, {})
        if blobs:
            lines = [f"# Azure Blob Containers ({name})", "", f"**Total:** {len(blobs)}", "",
                     _table_row(["Container", "Storage Account", "Public Access", "Lease Status"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in blobs.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("storage_account", "")),
                        str(info.get("public_access", "")),
                        str(info.get("lease_status", "")),
                    ]))
            self._write(cdir / "blob_containers.md", "\n".join(lines))

        # ---- Database: SQL Servers ----
        sql_servers = assets.get(SMT.AZURE_SQL_SERVER, {})
        if sql_servers:
            lines = [f"# Azure SQL Servers ({name})", "", f"**Total:** {len(sql_servers)}", "",
                     _table_row(["Server", "FQDN", "Version", "State", "Location"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in sql_servers.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("fully_qualified_domain_name", "")),
                        str(info.get("version", "")),
                        str(info.get("state", "")),
                        str(info.get("location", "")),
                    ]))
            self._write(cdir / "sql_servers.md", "\n".join(lines))

        # ---- Database: SQL Databases ----
        sql_dbs = assets.get(SMT.AZURE_SQL_DATABASE, {})
        if sql_dbs:
            lines = [f"# Azure SQL Databases ({name})", "", f"**Total:** {len(sql_dbs)}", "",
                     _table_row(["Database", "Server", "SKU", "Tier", "Status"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in sql_dbs.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("server_name", "")),
                        str(info.get("sku_name", "")),
                        str(info.get("sku_tier", "")),
                        str(info.get("status", "")),
                    ]))
            self._write(cdir / "sql_databases.md", "\n".join(lines))

        # ---- Database: Cosmos DB ----
        cosmos = assets.get(SMT.AZURE_COSMOS_ACCOUNT, {})
        if cosmos:
            lines = [f"# Azure Cosmos DB Accounts ({name})", "", f"**Total:** {len(cosmos)}", "",
                     _table_row(["Account", "Kind", "Endpoint", "Location", "State"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in cosmos.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("kind", "")),
                        str(info.get("document_endpoint", ""))[:80],
                        str(info.get("location", "")),
                        str(info.get("provisioning_state", "")),
                    ]))
            self._write(cdir / "cosmos_accounts.md", "\n".join(lines))

        # ---- Database: PostgreSQL Flexible Servers ----
        pg_servers = assets.get(SMT.AZURE_POSTGRES_SERVER, {})
        if pg_servers:
            lines = [f"# Azure PostgreSQL Servers ({name})", "", f"**Total:** {len(pg_servers)}", "",
                     _table_row(["Server", "FQDN", "Version", "SKU", "Storage GB", "State"]),
                     _table_row(["---", "---", "---", "---", "---", "---"])]
            for uid, info in pg_servers.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("fully_qualified_domain_name", "")),
                        str(info.get("version", "")),
                        str(info.get("sku_name", "")),
                        str(info.get("storage_size_gb", "")),
                        str(info.get("state", "")),
                    ]))
            self._write(cdir / "postgres_servers.md", "\n".join(lines))

        # ---- Database: PostgreSQL Databases ----
        pg_dbs = assets.get(SMT.AZURE_POSTGRES_DATABASE, {})
        if pg_dbs:
            lines = [f"# Azure PostgreSQL Databases ({name})", "", f"**Total:** {len(pg_dbs)}", "",
                     _table_row(["Database", "Server", "Charset", "Collation"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in pg_dbs.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("server_name", "")),
                        str(info.get("charset", "")),
                        str(info.get("collation", "")),
                    ]))
            self._write(cdir / "postgres_databases.md", "\n".join(lines))

        # ---- Cache: Redis ----
        redis = assets.get(SMT.AZURE_REDIS_CACHE, {})
        if redis:
            lines = [f"# Azure Redis Caches ({name})", "", f"**Total:** {len(redis)}", "",
                     _table_row(["Cache", "Hostname", "Port", "SKU", "Version", "State"]),
                     _table_row(["---", "---", "---", "---", "---", "---"])]
            for uid, info in redis.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("host_name", "")),
                        str(info.get("ssl_port", info.get("port", ""))),
                        str(info.get("sku_name", "")),
                        str(info.get("redis_version", "")),
                        str(info.get("provisioning_state", "")),
                    ]))
            self._write(cdir / "redis_caches.md", "\n".join(lines))

        # ---- Monitor: Metric Alerts ----
        alerts = assets.get(SMT.AZURE_METRIC_ALERT, {})
        if alerts:
            lines = [f"# Azure Metric Alerts ({name})", "", f"**Total:** {len(alerts)}", "",
                     _table_row(["Alert", "Severity", "Enabled", "Description"]),
                     _table_row(["---", "---", "---", "---"])]
            for uid, info in alerts.items():
                if isinstance(info, dict):
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("severity", "")),
                        str(info.get("enabled", "")),
                        str(info.get("description", ""))[:150],
                    ]))
            self._write(cdir / "metric_alerts.md", "\n".join(lines))

        # ---- Monitor: Action Groups ----
        action_groups = assets.get(SMT.AZURE_ACTION_GROUP, {})
        if action_groups:
            lines = [f"# Azure Action Groups ({name})", "", f"**Total:** {len(action_groups)}", "",
                     _table_row(["Group", "Short Name", "Enabled", "Email Receivers", "Webhook Receivers"]),
                     _table_row(["---", "---", "---", "---", "---"])]
            for uid, info in action_groups.items():
                if isinstance(info, dict):
                    emails = info.get("email_receivers", [])
                    webhooks = info.get("webhook_receivers", [])
                    lines.append(_table_row([
                        info.get("name", uid),
                        str(info.get("group_short_name", "")),
                        str(info.get("enabled", "")),
                        str(len(emails)),
                        str(len(webhooks)),
                    ]))
            self._write(cdir / "action_groups.md", "\n".join(lines))

    # ---- SigNoz ----

    def _generate_signoz(self, name: str, ctype: str, assets: dict):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        cdir = self._connector_dir(name)

        services = assets.get(SMT.SIGNOZ_SERVICE, {})
        if services:
            lines = [f"# SigNoz Services ({name})", "", f"**Total:** {len(services)}", "",
                     _table_row(["Service"]), _table_row(["---"])]
            for uid, info in services.items():
                sname = info.get("name", uid) if isinstance(info, dict) else uid
                lines.append(_table_row([sname]))
            self._write(cdir / "services.md", "\n".join(lines))

        dashboards = assets.get(SMT.SIGNOZ_DASHBOARD, {})
        if dashboards:
            lines = [f"# SigNoz Dashboards ({name})", "", f"**Total:** {len(dashboards)}", "",
                     _table_row(["Dashboard", "ID"]), _table_row(["---", "---"])]
            for uid, info in dashboards.items():
                dname = info.get("title", info.get("name", uid)) if isinstance(info, dict) else uid
                lines.append(_table_row([dname, uid]))
            self._write(cdir / "dashboards.md", "\n".join(lines))

    # ---- Generic fallback ----

    def _generate_generic(self, name: str, ctype: str, assets: dict):
        """Generic generator for connector types without specific handling."""
        cdir = self._connector_dir(name)
        lines = [f"# {ctype} ({name})", ""]

        for model_type, items in assets.items():
            if not items:
                continue
            mt_name = _model_type_name(model_type)
            lines.extend([f"## {mt_name} ({len(items)})", "",
                          _table_row(["Name/ID", "Details"]), _table_row(["---", "---"])])
            for uid, info in items.items():
                if isinstance(info, dict):
                    iname = info.get("name", info.get("title", uid))
                    details = str({k: v for k, v in info.items() if k not in ("name", "title")})[:200]
                else:
                    iname = uid
                    details = str(info)[:200]
                lines.append(_table_row([iname, details]))
            lines.append("")

        self._write(cdir / "details.md", "\n".join(lines))

    # ---- Cross-service aggregation ----

    def generate_service_crossref(self, all_results: dict[str, dict]):
        """Generate cross_references/services.md by cross-referencing service names across connectors.

        Scans all connector assets for service-like entities and groups them by name.
        """
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        # Model types that represent "services"
        service_model_types = {
            SMT.DATADOG_SERVICE, SMT.SIGNOZ_SERVICE,
            SMT.KUBERNETES_SERVICE, SMT.EKS_SERVICE, SMT.GKE_SERVICE,
            SMT.KUBERNETES_DEPLOYMENT, SMT.EKS_DEPLOYMENT, SMT.GKE_DEPLOYMENT,
            SMT.ECS_SERVICE, SMT.GRAFANA_TEMPO_SERVICE,
            SMT.GCP_CLOUD_RUN_SERVICE,
            SMT.AZURE_AKS_SERVICE, SMT.AZURE_AKS_DEPLOYMENT,
        }

        # Collect: service_name -> [{connector, connector_type, model_type, info}]
        service_map: dict[str, list[dict]] = {}

        for connector_name, result in all_results.items():
            if result.get("error"):
                continue
            ctype = result.get("connector_type", "")
            assets = result.get("assets", {})

            for model_type, items in assets.items():
                if model_type not in service_model_types:
                    continue
                if not isinstance(items, dict):
                    continue

                for uid, info in items.items():
                    if isinstance(info, dict):
                        # AKS resources store name inside metadata dict
                        meta = info.get("metadata", {})
                        if isinstance(meta, dict) and "name" in meta:
                            svc_name = meta["name"]
                        else:
                            svc_name = info.get("name", info.get("service_name", uid))
                    else:
                        svc_name = uid

                    # Normalize name and skip ephemeral pod/job names
                    svc_name_normalized = str(svc_name).strip().lower()
                    if not svc_name_normalized:
                        continue
                    if _is_ephemeral_name(svc_name_normalized):
                        continue

                    if svc_name_normalized not in service_map:
                        service_map[svc_name_normalized] = []

                    service_map[svc_name_normalized].append({
                        "connector": connector_name,
                        "connector_type": ctype,
                        "model_type": _model_type_name(model_type),
                        "display_name": str(svc_name),
                    })

        if not service_map:
            return

        # Generate cross-reference file
        lines = [
            "# Discovered Services",
            "",
            f"**Total unique services:** {len(service_map)}",
            "",
            _table_row(["Service", "Found In", "Resource Types"]),
            _table_row(["---", "---", "---"]),
        ]

        for svc_name in sorted(service_map.keys()):
            entries = service_map[svc_name]
            display = entries[0]["display_name"]
            connectors = ", ".join(sorted(set(e["connector"] for e in entries)))
            types = ", ".join(sorted(set(e["model_type"] for e in entries)))
            lines.append(_table_row([display, connectors, types]))

        # Add detail sections for services that appear in 2+ connectors
        multi_connector = {k: v for k, v in service_map.items()
                          if len(set(e["connector"] for e in v)) >= 2}
        if multi_connector:
            lines.extend(["", "---", "", "## Multi-Source Services", ""])
            for svc_name in sorted(multi_connector.keys()):
                entries = multi_connector[svc_name]
                display = entries[0]["display_name"]
                lines.extend([
                    f"### {display}",
                    "",
                    _table_row(["Tool", "Type", "Resource"]),
                    _table_row(["---", "---", "---"]),
                ])
                for entry in entries:
                    lines.append(_table_row([
                        entry["connector"],
                        entry["connector_type"],
                        entry["model_type"],
                    ]))
                lines.append("")

        self._write(self.resources_dir / "cross_references" / "services.md", "\n".join(lines))

    # ---- Overview ----

    def generate_overview(self, all_results: dict[str, dict]):
        """Generate the top-level overview.md summarizing all connectors.

        Args:
            all_results: {connector_name: {connector_type: str, assets: dict, error: str|None}}
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            "# Infrastructure Overview",
            "",
            f"Last synced: {now}",
            "",
            "## Connected Tools",
            "",
            _table_row(["Tool", "Type", "Status", "Resources Discovered"]),
            _table_row(["---", "---", "---", "---"]),
        ]

        for name, result in sorted(all_results.items()):
            ctype = result.get("connector_type", "UNKNOWN")
            error = result.get("error")

            if error:
                lines.append(_table_row([name, ctype, "FAILED", str(error)[:100]]))
            else:
                assets = result.get("assets", {})
                summary_parts = []
                for model_type, items in assets.items():
                    if items:
                        mt_name = _model_type_name(model_type)
                        summary_parts.append(f"{len(items)} {mt_name}")
                summary = ", ".join(summary_parts[:5])
                if len(summary_parts) > 5:
                    summary += f", +{len(summary_parts) - 5} more"
                lines.append(_table_row([name, ctype, "OK", summary]))

        lines.extend([
            "",
            "## Directory Structure",
            "",
            "```",
            "resources/",
            "  connectors/",
            "    <name>/          - All assets for one connector",
            "      _summary.md    - Resource counts",
            "      dashboards.md  - Dashboard index",
            "      alerts.md      - Alert rules / monitors",
            "      services.md    - Discovered services",
            "      ...            - Other resource-type files",
            "  cross_references/",
            "    services.md      - Services seen across multiple connectors",
            "```",
            "",
            "## How to Use This Context",
            "",
            "Add to your CLAUDE.md or agent prompt:",
            "",
            "```",
            "My production infrastructure context is in ./resources/.",
            "Refer to this when investigating issues, writing queries, or understanding system topology.",
            "```",
            "",
        ])

        self._write(self.resources_dir / "overview.md", "\n".join(lines))
