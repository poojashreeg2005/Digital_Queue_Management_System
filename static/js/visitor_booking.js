document.addEventListener("DOMContentLoaded", function () {
    const purposeSelect = document.getElementById("purpose_id");
    const departmentSelect = document.getElementById("department_id");
    const departmentHelp = document.getElementById("department-help");
    const otherPurposeField = document.getElementById("other-purpose-field");
    const otherPurposeInput = document.getElementById("other_purpose");
    const departmentData = document.getElementById("purpose-departments-data");

    if (!purposeSelect || !departmentSelect || !departmentData) return;

    const allDepartments = Array.from(departmentSelect.options)
        .filter(function (option) {
            return option.value !== "";
        })
        .map(function (option) {
            return { value: option.value, label: option.textContent };
        });

    let purposeDepartments;
    try {
        purposeDepartments = JSON.parse(departmentData.textContent);
    } catch (error) {
        console.error("Could not load purpose-to-department options:", error);
        departmentHelp.textContent = "Department options could not be loaded. Please reload the form.";
        departmentSelect.disabled = true;
        return;
    }

    let preferredDepartmentId = departmentSelect.dataset.preselectedDepartment;

    const updatePurposeFields = function () {
        const selectedPurpose = purposeSelect.value;
        const isOther = selectedPurpose === "other";

        otherPurposeField.hidden = !isOther;
        otherPurposeInput.required = isOther;
        if (!isOther) otherPurposeInput.value = "";

        departmentSelect.textContent = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = selectedPurpose
            ? "Select department to visit"
            : "Select a visit purpose first";
        departmentSelect.appendChild(placeholder);

        const allowedIds = new Set((purposeDepartments[selectedPurpose] || []).map(String));
        const availableDepartments = allDepartments.filter(function (department) {
            return allowedIds.has(department.value);
        });

        availableDepartments.forEach(function (department) {
            const option = document.createElement("option");
            option.value = department.value;
            option.textContent = department.label;
            departmentSelect.appendChild(option);
        });

        departmentSelect.disabled = availableDepartments.length === 0;
        if (!selectedPurpose) {
            departmentHelp.textContent = "Choose a visit purpose to see the relevant departments.";
        } else if (availableDepartments.length === 0) {
            departmentHelp.textContent = "No active departments are configured for this purpose.";
        } else {
            departmentHelp.textContent = "Choose the department that best matches your visit.";
            const preferredIsAvailable = availableDepartments.some(function (department) {
                return department.value === preferredDepartmentId;
            });
            departmentSelect.value = preferredIsAvailable
                ? preferredDepartmentId
                : availableDepartments[0].value;
        }

        preferredDepartmentId = "";
    };

    purposeSelect.addEventListener("change", updatePurposeFields);
    updatePurposeFields();
});
