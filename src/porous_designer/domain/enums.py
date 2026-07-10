"""Domain enumerations with explicit scientific terminology."""

from enum import Enum


class DomainShape(str, Enum):
    """Bounding domain geometry."""

    BOX = "box"
    CYLINDER = "cylinder"


class OriginConvention(str, Enum):
    """Coordinate origin placement for the domain."""

    CORNER_AT_ORIGIN = "corner_at_origin"
    CENTERED = "centered"


class StructureFamily(str, Enum):
    """Supported porous structure families."""

    # Sphere-pore lattices
    SC_SPHERICAL_PORES = "sc_spherical_pores"
    BCC_SPHERICAL_PORES = "bcc_spherical_pores"
    FCC_SPHERICAL_PORES = "fcc_spherical_pores"
    HCP_SPHERICAL_PORES = "hcp_spherical_pores"
    # TPMS structures
    GYROID = "gyroid"
    DIAMOND = "diamond"
    PRIMITIVE = "primitive"

    @property
    def is_sphere_lattice(self) -> bool:
        return self in {
            StructureFamily.SC_SPHERICAL_PORES,
            StructureFamily.BCC_SPHERICAL_PORES,
            StructureFamily.FCC_SPHERICAL_PORES,
            StructureFamily.HCP_SPHERICAL_PORES,
        }

    @property
    def is_tpms(self) -> bool:
        return self in {
            StructureFamily.GYROID,
            StructureFamily.DIAMOND,
            StructureFamily.PRIMITIVE,
        }

    @property
    def supports_step(self) -> bool:
        """STEP export is reliable only for sphere-pore lattices."""
        return self.is_sphere_lattice

    @property
    def legacy_lattice_key(self) -> str | None:
        """Map to porousgen.py lattice key for migration."""
        mapping = {
            StructureFamily.SC_SPHERICAL_PORES: "sc",
            StructureFamily.BCC_SPHERICAL_PORES: "bcc",
            StructureFamily.FCC_SPHERICAL_PORES: "fcc",
            StructureFamily.HCP_SPHERICAL_PORES: "hcp",
            StructureFamily.GYROID: "gyroid",
        }
        return mapping.get(self)


class ExportFormat(str, Enum):
    STL = "stl"
    STEP = "step"
    NPZ = "npz"
    YAML = "yaml"
    JSON = "json"
    HTML = "html"
    PNG = "png"


class RunStatus(str, Enum):
    """Blackboard lifecycle states."""

    CREATED = "created"
    PARSING = "parsing"
    NEEDS_USER_REVIEW = "needs_user_review"
    SPECIFICATION_APPROVED = "specification_approved"
    FEASIBILITY_CHECKING = "feasibility_checking"
    INFEASIBLE = "infeasible"
    PREVIEW_GENERATING = "preview_generating"
    PREVIEW_READY = "preview_ready"
    FINAL_GENERATING = "final_generating"
    VALIDATING = "validating"
    REPAIRING = "repairing"
    PASSED = "passed"
    FAILED = "failed"
    EXPORTED = "exported"
    CANCELLED = "cancelled"


class ValidationStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NOT_MEASURED = "not_measured"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FeasibilityStatus(str, Enum):
    FEASIBLE = "feasible"
    CONDITIONALLY_FEASIBLE = "conditionally_feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"


class ErrorCode(str, Enum):
    SPEC_AMBIGUOUS = "spec_ambiguous"
    SPEC_INVALID = "spec_invalid"
    SPEC_INFEASIBLE = "spec_infeasible"
    MEMORY_ESTIMATE_EXCEEDED = "memory_estimate_exceeded"
    POROSITY_TARGET_UNREACHABLE = "porosity_target_unreachable"
    GEOMETRY_EMPTY = "geometry_empty"
    GEOMETRY_DISCONNECTED = "geometry_disconnected"
    MESH_NOT_WATERTIGHT = "mesh_not_watertight"
    WALL_THICKNESS_VIOLATION = "wall_thickness_violation"
    THROAT_SIZE_VIOLATION = "throat_size_violation"
    PORE_CONNECTIVITY_FAILURE = "pore_connectivity_failure"
    STEP_BOOLEAN_FAILURE = "step_boolean_failure"
    STEP_VALIDATION_FAILURE = "step_validation_failure"
    EXPORT_FAILURE = "export_failure"
    LLM_SCHEMA_FAILURE = "llm_schema_failure"
    USER_CANCELLED = "user_cancelled"


class LLMMode(str, Enum):
    STRUCTURED_ONLY = "structured_only"
    ASSISTED = "assisted"
