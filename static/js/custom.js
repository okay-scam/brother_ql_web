function onPrinterChange() {
    const printerSelect = document.getElementById('printerSelect');
    const selectedOption = printerSelect.options[printerSelect.selectedIndex];
    const defaultLabel = selectedOption.getAttribute('data-label');
    const printButton = document.getElementById('printButton');
    const printButtonIcon = printButton.querySelector('span.glyphicon'); // Get icon
    const navBar = document.querySelector('.navbar'); // Get the navbar element

    // Store the selected printer index in localStorage
    localStorage.setItem('lastSelectedPrinterIndex', printerSelect.value);

    // Update the selected printer name display
    const category = selectedOption.parentElement.label; // Get category from optgroup label
    document.getElementById('selectedPrinterName').textContent =
        `${category} - ${selectedOption.text}`;

    // Update print button text
    printButton.textContent = ` Print ${category}`; // Set text, keeping space for icon
    printButton.insertBefore(printButtonIcon, printButton.firstChild); // Re-add icon

    // Update print button color based on category
    printButton.classList.remove('btn-category-east', 'btn-category-main'); // Remove existing category classes
    navBar.classList.remove('navbar-category-east', 'navbar-category-main'); // Remove existing navbar category classes

    if (category === 'East') {
        printButton.classList.add('btn-category-east');
        navBar.classList.add('navbar-category-east');
    } else if (category === 'Main') {
        printButton.classList.add('btn-category-main');
        navBar.classList.add('navbar-category-main');
    } // Add more else if blocks for other categories if needed

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

// Call onPrinterChange on initial load to set the correct button state
document.addEventListener('DOMContentLoaded', () => {
    const savedPrinterIndex = localStorage.getItem('lastSelectedPrinterIndex');
    if (savedPrinterIndex !== null) {
        const printerSelect = document.getElementById('printerSelect');
        // Check if an option with the saved value exists
        const optionExists = printerSelect.querySelector(`option[value="${savedPrinterIndex}"]`);
        if (optionExists) {
            printerSelect.value = savedPrinterIndex;
        } else {
            // Optional: Clear invalid index from storage if it doesn't match any option
            // localStorage.removeItem('lastSelectedPrinterIndex'); 
            console.warn(`Saved printer index "${savedPrinterIndex}" not found in options.`);
        }
    }
    // Now call onPrinterChange to apply the (potentially restored) selection to the UI
    onPrinterChange();
}); 