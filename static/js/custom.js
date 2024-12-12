function onPrinterChange() {
    const printerSelect = document.getElementById('printerSelect');
    const selectedOption = printerSelect.options[printerSelect.selectedIndex];
    const defaultLabel = selectedOption.getAttribute('data-label');

    // Update the selected printer name display
    document.getElementById('selectedPrinterName').textContent = selectedOption.text;

    // Set the label size to match the printer's default
    const labelSizeSelect = document.getElementById('labelSize');
    for (let i = 0; i < labelSizeSelect.options.length; i++) {
        if (labelSizeSelect.options[i].value === defaultLabel) {
            labelSizeSelect.selectedIndex = i;
            break;
        }
    }

    // Trigger preview update
    preview();
} 