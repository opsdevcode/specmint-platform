package v1alpha1

// Trusted DeliverySpecification contract. Callers never submit this file.
#CapabilityID: =~"^[a-z][a-z0-9]*(\\.[a-z][a-z0-9]*)+$"

#DeliverySpecification: {
	apiVersion: "specs.opsdevcode.io/v1alpha1"
	kind:       "DeliverySpecification"
	metadata: {
		id: =~"^ds-[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$"
	}
	spec: {
		owner:  =~"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"
		intent: =~"^.{1,500}$"
		target: {
			repository: =~"^https://.+"
		}
		environment?: {
			name: =~"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$"
		}
		required_capabilities: [...#CapabilityID]
		required_capabilities: [_, ...]
		constraints: {
			recorded_baseline_approved: bool
		}
		required_evidence: [...string]
		required_evidence: [...=~"^[A-Za-z0-9._-]+$"] | *[]
		exception_rules: {
			allow_unexpired: bool | *false
		}
		convergence: {
			compare:                  "on_demand"
			unknown_is_not_compliant: bool | *true
		}
		status: "draft" | "active" | "paused" | "retired"
	}
}

instance: #DeliverySpecification
