{{- define "corelab.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "corelab.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "corelab.labels" -}}
app.kubernetes.io/name: {{ include "corelab.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "corelab.selectorLabels" -}}
app.kubernetes.io/name: {{ include "corelab.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "corelab.ollamaHost" -}}
http://{{ include "corelab.fullname" . }}-ollama:{{ .Values.ollama.port }}
{{- end -}}
