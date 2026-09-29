package v1alpha1

// Trusted AutomationSpecification contract. Callers never submit this file.
// No credentials, URLs, or platform endpoints.

#AutomationSpecification: {
	apiVersion: "automations.opsdevcode.io/v1alpha1"
	kind:       "AutomationSpecification"
	metadata: {
		id: =~"^as-[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$"
	}
	spec: {
		owner:  =~"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"
		intent: =~"^.{1,500}$"
		automation: {
			type:    "local.sandbox.ensure_marker"
			version: "v1alpha1"
		}
		placement: {
			sandbox: =~"^[a-z][a-z0-9-]{0,62}$"
		}
		required_evidence: [...=~"^[A-Za-z0-9._-]+$"] | *[]
		constraints: {
			require_authorization:    bool | *true
			allow_platform_mutation: false
		}
		status: "draft" | "active" | "paused" | "retired"
	}
}

instance: #AutomationSpecification
