{{- define "zortenet.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "zortenet.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "zortenet.labels" -}}
app.kubernetes.io/name: {{ include "zortenet.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "zortenet.selectorLabels" -}}
app.kubernetes.io/name: {{ include "zortenet.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "zortenet.ollamaHost" -}}
http://{{ include "zortenet.fullname" . }}-ollama:{{ .Values.ollama.port }}
{{- end -}}
