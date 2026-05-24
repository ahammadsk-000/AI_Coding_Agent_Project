{{/* Chart name, overridable */}}
{{- define "aca.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully-qualified app name */}}
{{- define "aca.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" (include "aca.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* Common labels */}}
{{- define "aca.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "aca.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Per-component selector labels. Pass a dict: (dict "ctx" . "component" "api") */}}
{{- define "aca.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aca.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* Resolve an image with the optional global registry prefix */}}
{{- define "aca.image" -}}
{{- $reg := .ctx.Values.global.imageRegistry -}}
{{- if $reg -}}
{{- printf "%s%s" $reg .image -}}
{{- else -}}
{{- .image -}}
{{- end -}}
{{- end -}}

{{/* ServiceAccount name */}}
{{- define "aca.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (printf "%s-sa" (include "aca.fullname" .)) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Component-scoped resource name, e.g. aca-api */}}
{{- define "aca.componentName" -}}
{{- printf "%s-%s" (include "aca.fullname" .ctx) .component -}}
{{- end -}}

{{/* DATABASE_URL assembled from secret values + postgres service name */}}
{{- define "aca.databaseUrl" -}}
{{- printf "postgresql+asyncpg://%s:%s@%s-postgres:%d/%s" .Values.secrets.postgresUser .Values.secrets.postgresPassword (include "aca.fullname" .) (int .Values.postgres.port) .Values.secrets.postgresDb -}}
{{- end -}}

{{/* REDIS_URL */}}
{{- define "aca.redisUrl" -}}
{{- printf "redis://%s-redis:%d/0" (include "aca.fullname" .) (int .Values.redis.port) -}}
{{- end -}}

{{/* QDRANT_URL */}}
{{- define "aca.qdrantUrl" -}}
{{- printf "http://%s-qdrant:%d" (include "aca.fullname" .) (int .Values.qdrant.httpPort) -}}
{{- end -}}
