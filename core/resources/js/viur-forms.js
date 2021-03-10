$(document).ready(function () {

    // ---- Date Bones ----

    function viurBonesDateUpdate(boneName) {
        var realBoneName = boneName.substr(0, boneName.length - 5); // Cut off any tailing -date or -time strings
        var val = $("input[name='" + realBoneName + "-date']").val() + " " + $("input[name='" + realBoneName + "-time']").val();
        $("input[name='" + realBoneName + "']").val(val);
    }

    $(".js-viur-bones-date-doubleinput").each(function () {
        $("input[name='" + $(this).attr("name") + "-date']").change(function () {
            viurBonesDateUpdate($(this).attr("name"));
        });
        $("input[name='" + $(this).attr("name") + "-time']").change(function () {
            viurBonesDateUpdate($(this).attr("name"));
        })
    });

    // ---- Relational.Treeitem.File Bones ----

    function viurBonesFileCreateNewInputGroup(reordableArea) {
        // Creates the HTML that represents one file inside a multiple file bone
        var tpl = "";
        tpl += '<div class="vi-file input-group js-viur-bones-file-reordable-item" data-multiple="1" draggable="true">';
        tpl += '<div class="vi-file-multi-bone-preview-img"></div>';
        tpl += '<span class="input"></span>';
        tpl += '<button class="btn icon edit js-viur-bones-file-upload-file-button" type="button">Bearbeiten</button>';
        tpl += '<button class="btn icon cancel btn-vDanger js-viur-bones-file-remove-file" type="button">Entfernen</button>'
        tpl += '<span class="uploader"></span>';
        tpl += '<input type="hidden" name="' + reordableArea.data("name") + '.' + reordableArea.children().length + '.key" value="">';
        tpl += '</div>';
        var res = $(tpl);
        viurBonesFileRebindInputGroupEvents(res);
        viurBonesFileRebindFileRemoveButton(res.find(".js-viur-bones-file-remove-file"));
        viurBonesFileRebindFileUploadButton(res.find(".js-viur-bones-file-upload-file-button"));
        return res;
    }

    function viurBonesFileRebindFileUploadButton(elems) {
        elems.click(function () {
            // Ensure that the upload button inside inputGroups works
            var inputGroup = $(this).parent();
            var ulElement = $("<input type='file'>");
            ulElement.change(function () {
                if (ulElement.get()[0].files.length == 0) {
                    /* No file has been selected */
                    return;
                }
                inputGroup.find("span[class='input']").html("");
                inputGroup.find("span[class='uploader']").children().remove();
                inputGroup.find("input[type='hidden']").val("");
                inputGroup.toggleClass("is-empty", true);
                viurBonesFileUploadIn(inputGroup, ulElement.get()[0].files[0], false);
            });
            ulElement.click();
        });
    }

    viurBonesFileRebindFileUploadButton($(".js-viur-bones-file-upload-file-button"));

    function viurBonesFileRebindFileRemoveButton(elems) {
        // Ensure that the delete button inside inputGroups works
        elems.click(function () {
            var inputGroup = $(this).parent();
            if (inputGroup.data("multiple") == "1") {
                // We just remove that file from the list
                inputGroup.remove()
            } else {
                // Reset this bone to empty again
                inputGroup.find("span[class='input']").html("");
                inputGroup.find("span[class='uploader']").children().remove();
                inputGroup.find("input[type='hidden']").val("");
                inputGroup.find("div[class~='vi-file-multi-bone-preview-img'], div[class~='vi-file-bone-preview-img']").css("background-image", "");
                inputGroup.toggleClass("is-empty", true);
            }
        });
    }

    viurBonesFileRebindFileRemoveButton($(".js-viur-bones-file-remove-file"));

    function viurBonesFileRebindInputGroupEvents(elems) {
        // Attaches the events needed to handle delete, upload & drag'n'drop inside an inputGroup
        elems.bind("dragstart", function (evt) {
            $(this).toggleClass("reodableAreaItemIsDragged", true);
            // Our draggable elements don't have an id, so we'll use the index from our input
            // field to identify the object which gets dragged later on
            evt.originalEvent.dataTransfer.setData("text", $(evt.target).find("input[type='hidden']").attr("name"));
        }).bind("dragend", function (evt) {
            $(this).toggleClass("reodableAreaItemIsDragged", false);
        });
    }

    viurBonesFileRebindInputGroupEvents($(".js-viur-bones-file-reordable-item"));


    function viurBonesFileUploadIn(inputGroup, file, removeGroupOnFailure) {
        // Replace / set the file that's currently displayed by one inputGroup
        // Used for both (multiple=False/True) cases
        var boneName = inputGroup.data("name");

        function updateProgressBar(evt) {
            var percentDone = (evt.loaded / evt.total) * 100;
            inputGroup.find("progress[class='progress']").attr("value", percentDone);
        }

        function uploadDone(evt) {
            var parsedJson = $.parseJSON(evt.srcElement.response);
            if (parsedJson.values && parsedJson.values.length > 0) {  // We have one successful upload
                var fileData = parsedJson.values[0];
                inputGroup.find("span[class='input']").append(document.createTextNode(fileData.name));
                inputGroup.find("span[class='uploader']").children().remove();
                inputGroup.find("input[type='hidden']").val(fileData.key);
                if (fileData.servingurl) {
                    inputGroup.find("div[class~='vi-file-multi-bone-preview-img'], div[class~='vi-file-bone-preview-img']").css("background-image", "url("+fileData.servingurl+"=s150)")
                } else {
                    inputGroup.find("div[class~='vi-file-multi-bone-preview-img'], div[class~='vi-file-bone-preview-img']").css("background-image", "")
                }

                inputGroup.toggleClass("is-empty", false);
            }
        }

        // Fetch a fresh security key
        $.ajax({
            "url": "/json/skey",
            "type": "post",
            "success": function (result) {
                inputGroup.find("span[class='uploader']").append($("<progress min='0' max='100' value='0' class='progress'></progress>"));
                // Use that security key to determine the url we have to upload to
                $.ajax({
                    "url": "/json/file/getUploadURL",
                    "type": "post",
                    "data": {"skey": result.substr(1, result.length - 2)},
                    "success": function (result) {
                        // Construct a new XMLHttpRequest to upload the file
                        var fd = new FormData();
                        fd.append("file", file);
                        var request = new XMLHttpRequest();
                        request.open("POST", result);
                        request.addEventListener("progress", updateProgressBar);
                        request.addEventListener("load", uploadDone);
                        request.send(fd);
                    }
                });
            }
        });
    }

    $(".js-viur-bones-file-reordable-area").bind("dragover", function (evt) {
        // Determine where the drop should be placed and show an visual indicator
        var afterElement = null;
        $(this).children().each(function (idx) {
            // Determine after which element the dragged one should be inserted (null if before the first one)
            if ($(this).offset().top + ($(this).height() / 1.5) < evt.pageY) {
                afterElement = $(this);
            }
        });
        $(this).children().toggleClass("reodableAreaInsertAfter", false).toggleClass("reodableAreaInsertBefore", false);
        if (afterElement) {
            afterElement.toggleClass("reodableAreaInsertAfter", true);
        } else {
            $(this).children().first().toggleClass("reodableAreaInsertBefore", true);
        }
        evt.preventDefault();
        return false;
    }).bind("drop", function (evt) {
        // We got a drop (either it's a internal move operation or we've got a bunch of files)
        var afterElement = null;
        $(this).children().each(function (idx) {
            // Determine after which element the dragged one should be inserted (null if before the first one)
            if ($(this).offset().top + ($(this).height() / 1.5) < evt.pageY) {
                afterElement = $(this);
            }
        });
        var data = evt.originalEvent.dataTransfer.getData("text");
        if (data) {
            // It's an internal move operation; just relocate the entry
            var draggedElement = $(this).find("input[type='hidden'][name='" + data + "']").parent();
            if (afterElement) {
                draggedElement.insertAfter(afterElement);
            } else {
                draggedElement.insertBefore($(this).children().first());
            }
            // Reset CSS States
            draggedElement.toggleClass("reodableAreaItemIsDragged", false);
        } else if (evt.originalEvent.dataTransfer.files.length > 0) {
            // We got file(s) from the outside; create a new inputGroup for each and start uploading
            for (var i = 0; i < evt.originalEvent.dataTransfer.files.length; i++) {
                var inputGroup = viurBonesFileCreateNewInputGroup($(this));
                if (afterElement) {
                    inputGroup.insertAfter(afterElement);
                } else if ($(this).children().length > 0) {
                    inputGroup.insertBefore($(this).children().first());
                } else {
                    $(this).append(inputGroup);
                }
                viurBonesFileUploadIn(inputGroup, evt.originalEvent.dataTransfer.files[i], true);
            }
        }
        $(this).children().toggleClass("reodableAreaInsertAfter", false).toggleClass("reodableAreaInsertBefore", false);
        $(this).children().find("input[type='hidden']").each(function (idx) {
            // Update the index thats inside the name-property of our input fields (ie bone._index_.key)
            // so it matches the currently displayed order
            var name = $(this).attr("name");
            $(this).attr("name", name.substr(0, name.indexOf(".")) + "." + idx.toString() + ".key");
        });
        evt.preventDefault();
        return false;
    }).bind("dragleave", function (evt) {
        // Stop highlighting if we're outside our drop area
        if ($(this).offset().top > evt.pageY || ($(this).offset().top + $(this).height()) < evt.pageY || $(this).offset().left > evt.pageX || ($(this).offset().left + $(this).width()) < evt.pageX) {
            $(this).children().toggleClass("reodableAreaInsertAfter", false).toggleClass("reodableAreaInsertBefore", false);
        }
    }).bind("dragenter", function (evt) {
        // Accept all drag-enter events by default
        evt.preventDefault();
        return false;
    });


    $(".js-viur-bones-file-add-files").click(function () {
        // The user clicked the button to add new files to a multiple=True fileBone. Open the chooser,
        // create a new inputGroup for each and start uploading
        var oldThis = $(this);
        var ulElement = $("<input type='file' multiple>");
        ulElement.change(function () {
            if (ulElement.get()[0].files.length == 0) {
                /* No file has been selected */
                return;
            }
            for (var i = 0; i < ulElement.get()[0].files.length; i++) {
                var inputGroup = viurBonesFileCreateNewInputGroup(oldThis.parent().find("div[class~='vi-selection']"));
                oldThis.parent().find("div[class~='vi-selection']").append(inputGroup);
                viurBonesFileUploadIn(inputGroup, ulElement.get()[0].files[i], true);
            }
        });
        ulElement.click();
    });

    $(".js-viur-bones-file-uploadable-input-group").bind("dragenter dragover", function (evt) {
        // For multiple=False bones we'll also accept all drag events by default
        evt.preventDefault();
        return false;
    }).bind("drop", function (evt) {
        // If we got exactly one file we'll use it (ignored otherwhise)
        if (evt.originalEvent.dataTransfer.files.length == 1) {
            // We'll accept exactly one file
            viurBonesFileUploadIn($(this), evt.originalEvent.dataTransfer.files[0], false);
        }
        evt.preventDefault();
        return false
    });


    // ---- Str Bones ----

    function viurBonesStrRebindDeleteStrButton(elems) {
        // If clicked, remove the singeStrWrapper we are in
        elems.click(function (evt) {
            $(this).parent().remove();
            evt.preventDefault();
            return false;
        });
    }

    viurBonesStrRebindDeleteStrButton($(".js-viur-bones-str-delte-single-str-wrapper"));


    $(".js-viur-bones-str-language-selector").change(function () {
        // Show the corresponding text field(s)
        $(".js-viur-bones-str-language-wrapper[data-name='" + $(this).data("name") + "']").css("display", "none");
        var selector = "[data-name='" + $(this).data("name") + "'][data-lang='" + $(this).val() + "']";
        $(".js-viur-bones-str-language-wrapper" + selector).css("display", "");
    }).change();


    $(".js-viur-bones-str-add-single-str-wrapper").click(function (evt) {
        // create a new js-viur-bones-str-single-str-wrapper object and append it to the dom
        var wrapDataObj = $(this).parents(".js-viur-bones-str-language-wrapper").first();
        var boneName = "";
        if (wrapDataObj.length) {
            // We are multiple=True and have translations
            boneName = wrapDataObj.data("name") + '.' + wrapDataObj.data("lang");
        } else {
            // It's a multiple=True bone *without* translations
            wrapDataObj = $(this).parents(".js-viur-bones-str-multi-str-wrapper");
            boneName = wrapDataObj.data("name");
        }
        var tpl = "";
        tpl += '<div class="js-viur-bones-str-single-str-wrapper">';
        tpl += '<input class="input js-viur-bones-str-translated-single" type="text"';
        tpl += 'name="' + boneName + '"';
        tpl += 'value="">';
        tpl += '<button class="button js-viur-bones-str-delte-single-str-wrapper">Delete</button>';
        tpl += '</div>';
        var singleStrWrapper = $(tpl);
        singleStrWrapper.insertBefore($(this));
        viurBonesStrRebindDeleteStrButton(singleStrWrapper.find(".js-viur-bones-str-delte-single-str-wrapper"));
        evt.preventDefault();
        return false;
    });

    // ---- Str Bones ----

    $(".js-viur-bones-text-language-selector").change(function () {
        // Show the corresponding text field
        $(".js-viur-bones-text-language-wrapper[data-name='" + $(this).data("name") + "']").css("display", "none");
        var selector = "[data-name='" + $(this).data("name") + "'][data-lang='" + $(this).val() + "']";
        $(".js-viur-bones-text-language-wrapper" + selector).css("display", "");
    }).change();
});
